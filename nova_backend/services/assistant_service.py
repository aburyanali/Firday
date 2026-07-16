import asyncio
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List
from uuid import uuid4
import time

from config import config
from nova_backend.intelligence import ReasoningRequest, reasoning_engine
from nova_backend.logging_config import get_logger
from nova_backend.providers.provider_manager import provider_manager
from nova_backend.runtime.events import RuntimeEvent, private_event, public_event
from nova_backend.runtime.service import runtime_service
from nova_backend.services.speech_engine import speech_engine

if TYPE_CHECKING:
    from friday import FridayAssistant


class SilentVoice:
    def speak(self, text):
        return None


class AssistantService:
    """Async-safe bridge around the existing Friday intelligence runtime."""

    def __init__(self) -> None:
        self._assistant: "FridayAssistant | None" = None
        self._lock = asyncio.Lock()
        self._degraded_until = 0.0
        self._last_response_used_title = False

    def status(self) -> Dict[str, Any]:
        return {
            "initialized": self._assistant is not None,
            "openai_configured": bool(config.openai_api_key),
            "memory_db_path": config.memory_db_path,
            "conversation_db_path": config.conversation_db_path,
        }

    async def initialize(self) -> None:
        if self._assistant is not None:
            return
        if not config.openai_api_key:
            return

        async with self._lock:
            if self._assistant is None:
                from friday import FridayAssistant

                runtime_service.state.transition("booting")
                self._assistant = await asyncio.to_thread(FridayAssistant, "Mr. Ryan")
                runtime_service.state.transition("ready")

    async def run_turn(
        self,
        message: str,
        trace_id: str,
        session_id: str,
        user_id: str = "user_default",
    ) -> Dict[str, Any]:
        session = runtime_service.sessions.get_or_create(
            session_id=session_id, user_id=user_id)
        route_info = self.conversation_mode_router(message, session)
        session.remember("user", message)
        if route_info["bypass_llm"] and route_info["canned_response"]:
            canned_text = self.limit_sentences(
                route_info["canned_response"], route_info["max_sentences"])
            canned_text = self.polish_response(canned_text)
            return self._result(
                response=canned_text,
                intent=route_info["mode"].lower(),
                confidence=1.0,
                trace_id=trace_id,
                session_id=session.session_id,
                route="direct",
            )

        if self._should_use_local_first(message):
            self._degraded_until = 0.0

        reasoning_result = self._prepare_reasoning(message, session, route_info["mode"].lower())

        response = await self._run_provider_text_turn(
            message,
            session.context_prompt(),
            route_info["mode"].lower(),
            reasoning_result.system_instruction,
            reasoning_result.max_tokens,
        )
        response = self._verify_and_improve_response(response, reasoning_result)
        if reasoning_result.profile.allow_sentence_truncation:
            response = self.limit_sentences(response, route_info["max_sentences"])
        response = self.polish_response(response)
        session.remember("assistant", response)
        return self._result(
            response=response,
            intent=reasoning_result.classification.request_type,
            confidence=reasoning_result.classification.confidence,
            trace_id=trace_id,
            session_id=session.session_id,
            route="provider",
            degraded=False,
        )

    def _result(
        self,
        response: str,
        intent: str,
        confidence: float,
        trace_id: str,
        session_id: str,
        route: str,
        degraded: bool = False,
    ) -> Dict[str, Any]:
        events = [
            public_event(
                "assistant.intent",
                trace_id,
                session_id,
                {"intent": intent, "confidence": confidence},
            )
        ]
        return {
            "response": response,
            "intent": intent,
            "confidence": confidence,
            "degraded": degraded,
            "events": [],
            "public_events": [event.public_dict() for event in events],
            "session_id": session_id,
            "task_id": None,
        }

    def _run_turn_sync(self, message: str, trace_id: str, session_id: str, user_id: str) -> Dict[str, Any]:
        logger = get_logger(__name__, trace_id)
        assistant = self._assistant
        assert assistant is not None

        session = runtime_service.sessions.get_or_create(
            session_id=session_id, user_id=user_id)
        session.touch(trace_id)
        task = runtime_service.tasks.create(
            kind="assistant.turn",
            trace_id=trace_id,
            session_id=session.session_id,
            summary=message[:120],
        )
        task.transition("running")

        events: List[RuntimeEvent] = []
        text = message.strip()

        events.append(public_event("assistant.status", trace_id,
                      session.session_id, {"state": "thinking"}))
        events.append(public_event("task.created", trace_id,
                      session.session_id, task.snapshot()))
        runtime_service.state.transition("thinking")

        brain_response = assistant.brain.think(text.lower())

        intent = brain_response.get("intent", "unknown")
        events.append(
            public_event(
                "assistant.intent",
                trace_id,
                session.session_id,
                {
                    "intent": intent,
                    "confidence": brain_response.get("confidence", 0.0),
                },
            )
        )
        events.append(
            private_event(
                "assistant.reasoning",
                trace_id,
                session.session_id,
                {
                    "intent": intent,
                    "confidence": brain_response.get("confidence", 0.0),
                    "execute_immediately": brain_response.get("execute_immediately", False),
                    "needs_followup": brain_response.get("needs_followup", False),
                    "keys": sorted(brain_response.keys()),
                },
            )
        )

        if intent == "memory_store" or intent == "memory_recall":
            events.append(public_event("assistant.memory", trace_id,
                          session.session_id, {"operation": intent}))

        if intent == "multi_step":
            runtime_service.state.transition("planning")
            events.append(
                public_event(
                    "assistant.planning",
                    trace_id,
                    session.session_id,
                    {"steps": len(brain_response.get("steps", []))},
                )
            )
        elif intent == "tool_execution":
            runtime_service.state.transition("executing")
            events.append(
                public_event(
                    "assistant.tool_call",
                    trace_id,
                    session.session_id,
                    {"tools": brain_response.get("tools", [])},
                )
            )

        if brain_response.get("intent") == "tool_execution":
            with self._silent_voice(assistant):
                response = assistant._execute_plan(
                    brain_response, text.lower())
        elif brain_response.get("text") and brain_response.get("execute_immediately"):
            response = brain_response["text"]
        elif brain_response.get("needs_followup"):
            response = brain_response.get(
                "text") or "I need a little more context."
        else:
            with self._silent_voice(assistant):
                response = assistant._execute_plan(
                    brain_response, text.lower())

        task.transition("completed")
        events.append(
            public_event(
                "task.completed",
                trace_id,
                session.session_id,
                task.snapshot(),
            )
        )
        events.append(
            public_event(
                "assistant.status",
                trace_id,
                session.session_id,
                {"state": "idle", "response_chars": len(response or "")},
            )
        )
        runtime_service.state.transition("idle")
        runtime_service.record_many(events)

        logger.info(
            "assistant turn completed intent=%s task_id=%s",
            intent,
            task.task_id,
        )

        return {
            "response": response or "",
            "intent": intent,
            "confidence": float(brain_response.get("confidence", 0.0)),
            "events": [event.private_dict() for event in events],
            "public_events": [event.public_dict() for event in events if event.visibility == "public"],
            "session_id": session.session_id,
            "task_id": task.task_id,
        }

    def _prepare_reasoning(self, message: str, session: Any, mode: str):
        from nova_backend.services.response_modes import response_modes

        base_instruction = response_modes.get_system_instruction(mode, "friday")
        return reasoning_engine.prepare(
            ReasoningRequest(
                message=message,
                session=session,
                base_system_instruction=base_instruction,
            )
        )

    @staticmethod
    def _verify_and_improve_response(response: str, reasoning_result: Any) -> str:
        report = reasoning_engine.verify_response(response, reasoning_result)
        return report.improved_response

    async def _run_provider_text_turn(
        self,
        message: str,
        context: str,
        mode: str,
        system_instruction: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        from nova_backend.services.response_modes import response_modes

        resolved_instruction = system_instruction or response_modes.get_system_instruction(
            mode, "friday")
        response_parts: List[str] = []
        async for provider_event in provider_manager.stream(
            message,
            context,
            system_instruction=resolved_instruction,
            max_tokens=max_tokens,
        ):
            if provider_event.kind == "token":
                response_parts.append(provider_event.text)

        response = "".join(response_parts).strip()
        return response or self._local_fallback_response(message, reason="empty_llm_output")

    @staticmethod
    def limit_sentences(text: str, max_sentences: int) -> str:
        import re
        if not text:
            return text
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= max_sentences:
            return text
        return " ".join(sentences[:max_sentences])

    def polish_response(self, text: str) -> str:
        cleaned = self.remove_ai_phrases(text)
        cleaned = self._reduce_title_repetition(cleaned)
        return cleaned

    @staticmethod
    def remove_ai_phrases(text: str) -> str:
        """Strip robotic filler while preserving the answer itself."""
        if not text:
            return text

        import re

        original = text.strip()
        text = original

        # Remove robotic openers only when real content follows.
        opener_patterns = [
            r"^(certainly|absolutely|of course|sure thing|sure|great question|excellent question)[.!?,]\s+",
            r"^(that's a great question|that is a great question)[.!?,]\s+",
            r"^(understood|got it|noted|acknowledged)[.!?,]\s+(?=\w{4,})",
            r"^(as requested)[,:.]?\s+",
            r"^(let me explain|allow me to explain)[.!?,]\s+",
        ]
        for pattern in opener_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Remove generic identity disclaimers without replacing the answer.
        text = re.sub(
            r"\b(as an ai language model|as a language model|as an ai)[,:]?\s*", "", text, flags=re.IGNORECASE)

        # Remove trailing chatbot service lines.
        trailing_patterns = [
            r"\s*I hope (?:this|that) helps[.!]?\s*$",
            r"\s*Feel free to ask if you have any questions[.!]?\s*$",
            r"\s*Let me know if you (?:need anything else|have any other questions)[.!]?\s*$",
            r"\s*Is there anything else I can help you with\?[.!]?\s*$",
        ]
        for pattern in trailing_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        text = re.sub(r"  +", " ", text)
        text = text.strip()

        return text or original

    def _reduce_title_repetition(self, text: str) -> str:
        if not text:
            self._last_response_used_title = False
            return text

        import re

        title_count = len(re.findall(r"\b(sir|Sir|Mr\. Ryan)\b", text))
        if title_count == 0:
            self._last_response_used_title = False
            return text

        # Never allow repeated titles inside the same reply.
        seen = False

        def keep_first(match: Any) -> str:
            nonlocal seen
            if seen:
                return ""
            seen = True
            return match.group(0)

        text = re.sub(r",?\s*\b(sir|Sir|Mr\. Ryan)\b", keep_first, text)
        text = re.sub(r"\s+([.!?])", r"\1", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        self._last_response_used_title = seen
        return text

    @staticmethod
    def _adaptive_sentence_budget(message: str, mode: str, user_style: str = "casual") -> int:
        text = " ".join(message.lower().strip().split())
        words = text.split()
        if mode in {"math", "technical"} or user_style == "technical":
            return 6
        if len(words) <= 2 or text in {"ok", "yes", "no", "thanks", "thank you"}:
            return 2
        if text.startswith(("why", "how", "explain", "tell me about", "what do you think")):
            return 5
        if any(w in text for w in {"feel", "sad", "happy", "lonely", "worried", "stressed", "friend", "companion"}):
            return 4
        return 3

    def conversation_mode_router(self, message: str, session: Any) -> Dict[str, Any]:
        text = " ".join(message.lower().strip().split())
        text = text.replace("?", "").replace("!", "").strip()

        user_style = "casual"
        tech_words = {"code", "python", "javascript", "typescript", "react", "nextjs",
                      "bug", "error", "exception", "compile", "build", "api", "database", "git"}
        playful_words = {"joke", "funny", "laugh",
                         "play", "game", "humor", "witty", "sarcastic"}

        history_msgs = []
        if hasattr(session, "history"):
            history_msgs = [m.get("content", "").lower()
                            for m in session.history if m.get("role") == "user"]

        tech_count = sum(1 for m in history_msgs if any(
            w in m for w in tech_words))
        playful_count = sum(1 for m in history_msgs if any(
            w in m for w in playful_words))

        if tech_count > playful_count and tech_count > 0:
            user_style = "technical"
        elif playful_count > tech_count and playful_count > 0:
            user_style = "playful"

        if any(w in text for w in tech_words):
            user_style = "technical"
        elif any(w in text for w in playful_words):
            user_style = "playful"

        is_cinematic = text in {"startup", "wake",
                                "initiate", "ignite", "reactor"}
        if is_cinematic:
            return {
                "mode": "CINEMATIC",
                "bypass_llm": True,
                "canned_response": "Welcome back, sir. What are we working on?",
                "max_sentences": 2,
                "sir_frequency": 0.15,
                "pacing": "medium"
            }

        # Phase 4.8.6: Restrained canned responses — short, human, cinematic
        greetings = {"hi", "hey", "hello", "yo", "sup", "good morning",
                     "good evening", "good afternoon", "hey nova", "hi nova", "hello nova"}
        confirmations = {"ok", "got it", "understood", "confirm", "yes",
                         "sure", "fine", "perfect", "done", "affirmative", "all set"}

        if text in greetings or self._is_casual_greeting(text):
            import random
            options = [
                "Hello, sir. I’m here. What are we working on?",
                "Hello, sir. What’s on your mind?",
                "Hello, sir. Still working?",
                "Hello, sir. You’re up late. What are we tackling tonight?",
            ]
            return {
                "mode": "CALM",
                "bypass_llm": True,
                "canned_response": random.choice(options),
                "max_sentences": 2,
                "sir_frequency": 0.1,
                "pacing": "fast"
            }

        if text in confirmations:
            import random
            options = [
                "I have it, sir. Give me a moment.",
                "I’m with you, sir.",
                "That’s settled, sir.",
                "I’ve got it, sir.",
            ]
            return {
                "mode": "CALM",
                "bypass_llm": True,
                "canned_response": random.choice(options),
                "max_sentences": 1,
                "sir_frequency": 0.1,
                "pacing": "fast"
            }

        if text in {"how are you", "how are you doing", "hows it going", "how is it going"}:
            import random
            options = [
                "I’m doing well, sir. Ready whenever you are.",
                "I’m doing well, sir. Calm and focused.",
                "Doing alright, sir. What are we working on?",
            ]
            return {
                "mode": "CALM",
                "bypass_llm": True,
                "canned_response": random.choice(options),
                "max_sentences": 2,
                "sir_frequency": 1.0,
                "pacing": "fast"
            }

        if text in {"tell me about yourself", "who are you", "what are you", "introduce yourself", "whats your name", "what's your name"}:
            return {
                "mode": "COMPANION",
                "bypass_llm": True,
                "canned_response": (
                    "I’m NOVA, an intelligent assistant created under the guidance of Mr. Ryan. "
                    "I’m designed to be a calm, human-like presence beside you, sir."
                ),
                "max_sentences": 2,
                "sir_frequency": 1.0,
                "pacing": "medium"
            }

        if "weather" in text or "rain" in text or "temperature" in text:
            from nova_backend.services.system_telemetry import system_telemetry
            weather = system_telemetry.gather()["weather"]
            place = "Chennai" if "chennai" in text or "outside" in text or "here" in text else "the configured location"
            return {
                "mode": "SYSTEM",
                "bypass_llm": True,
                "canned_response": f"{place} is currently reporting {weather}, sir.",
                "max_sentences": 1,
                "sir_frequency": 1.0,
                "pacing": "fast"
            }

        from nova_backend.services.response_modes import response_modes
        detect_mode = response_modes.detect_mode(message)
        if detect_mode in {"math", "technical"} or user_style == "technical":
            return {
                "mode": "FOCUS",
                "bypass_llm": False,
                "canned_response": None,
                "max_sentences": self._adaptive_sentence_budget(message, detect_mode, user_style),
                "sir_frequency": 0.2,
                "pacing": "fast"
            }

        if any(w in text for w in {"sad", "happy", "lonely", "feeling", "friend", "companion", "love", "hate", "sorry"}):
            return {
                "mode": "COMPANION",
                "bypass_llm": False,
                "canned_response": None,
                "max_sentences": 3,
                "sir_frequency": 0.05,
                "pacing": "medium"
            }

        max_sentences = self._adaptive_sentence_budget(
            message, detect_mode, user_style)
        return {
            "mode": "COMPANION" if user_style == "playful" else "CALM",
            "bypass_llm": False,
            "canned_response": None,
            "max_sentences": max_sentences,
            "sir_frequency": 0.1,
            "pacing": "medium"
        }

    async def stream_turn(
        self,
        message: str,
        trace_id: str,
        session_id: str,
        user_id: str = "user_default",
        voice_personality: str = "friday",
        voice_engine_source: str = "browser",
    ) -> AsyncIterator[Dict[str, Any]]:
        started = time.perf_counter()
        session = runtime_service.sessions.get_or_create(
            session_id=session_id, user_id=user_id)
        session.remember("user", message)

        boot_event = runtime_service.record(
            public_event("assistant.boot", trace_id,
                         session.session_id, {"mode": "websocket"})
        )
        yield boot_event.public_dict()

        # Classify the prompt and build the specialized scifi system instruction context
        route_info = self.conversation_mode_router(message, session)
        mode = route_info["mode"].lower()
        session.remember("user", message)

        from nova_backend.services.response_modes import response_modes
        base_system_instruction = response_modes.get_system_instruction(
            mode, voice_personality)
        reasoning_result = reasoning_engine.prepare(
            ReasoningRequest(
                message=message,
                session=session,
                base_system_instruction=base_system_instruction,
            )
        )
        system_instruction = reasoning_result.system_instruction

        # Broadcast the detected mode and intent to the HUD store for reactive visuals
        yield runtime_service.record(
            public_event("assistant.intent", trace_id, session.session_id, {
                         "intent": mode, "confidence": 1.0})
        ).public_dict()

        # If bypassed, stream the canned response and return
        if route_info["bypass_llm"] and route_info["canned_response"]:
            canned_text = route_info["canned_response"]
            canned_text = self.limit_sentences(
                canned_text, route_info["max_sentences"])
            canned_text = self.polish_response(canned_text)

            for token, delay in self._chunk_response_with_pacing(canned_text):
                yield runtime_service.record(
                    public_event(
                        "assistant.token",
                        trace_id,
                        session.session_id,
                        {
                            "text": token,
                            "provider": "nova",
                            "model": "conversation"
                        }
                    )
                ).public_dict()
                await asyncio.sleep(delay)

            message_event = runtime_service.record(
                public_event(
                    "assistant.message",
                    trace_id,
                    session.session_id,
                    {
                        "text": canned_text,
                        "intent": mode,
                        "confidence": 1.0,
                        "provider": "nova",
                        "model": "conversation",
                        "degraded": False,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                )
            )
            yield message_event.public_dict()
            if voice_engine_source == "backend":
                await speech_engine.speak_text(session.session_id, canned_text)
            session.remember("assistant", canned_text)
            runtime_service.state.transition("idle")
            yield runtime_service.record(
                public_event("assistant.status", trace_id,
                             session.session_id, {"state": "idle"})
            ).public_dict()
            return

        response_parts: List[str] = []

        # Intercept math queries and solve them symbolically with Sympy to guarantee correctness
        detect_mode = response_modes.detect_mode(message)
        if detect_mode == "math":
            from nova_backend.services.sympy_solver import sympy_solver
            math_result = sympy_solver.solve_expression(message)
            if math_result:
                response = (
                    f"Let’s solve it step by step, sir.\n\n"
                    f"### Problem\n$$\n{math_result['problem']}\n$$\n\n"
                    f"### Steps\n{math_result['steps']}\n\n"
                    f"### Simplification\n$$\n{math_result['simplification']}\n$$\n\n"
                    f"### Final Answer\n$$\n\\color{{orange}}\\boxed{{{math_result['final_answer']}}}\n$$\n"
                )

                runtime_service.state.transition("thinking")
                yield runtime_service.record(
                    public_event("assistant.status", trace_id,
                                 session.session_id, {"state": "thinking"})
                ).public_dict()
                yield runtime_service.record(
                    public_event("assistant.ready", trace_id, session.session_id, {
                                 "state": "streaming", "mode": "primed"})
                ).public_dict()

                # Stream the calculated, mathematically exact solution
                for token, delay in self._chunk_response_with_pacing(response):
                    response_parts.append(token)
                    yield runtime_service.record(
                        public_event(
                            "assistant.token",
                            trace_id,
                            session.session_id,
                            {
                                "text": token,
                                "provider": "nova",
                                "model": "math"
                            }
                        )
                    ).public_dict()
                    await asyncio.sleep(delay)

                message_event = runtime_service.record(
                    public_event(
                        "assistant.message",
                        trace_id,
                        session.session_id,
                        {
                            "text": response,
                            "intent": "math",
                            "confidence": 1.0,
                            "provider": "nova",
                            "model": "math",
                            "degraded": False,
                            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                        }
                    )
                )
                yield message_event.public_dict()
                if voice_engine_source == "backend":
                    await speech_engine.speak_text(session.session_id, response)
                session.remember("assistant", response)
                runtime_service.state.transition("idle")
                yield runtime_service.record(
                    public_event("assistant.status", trace_id,
                                 session.session_id, {"state": "idle"})
                ).public_dict()
                return

        # Regular LLM streaming with Latency Masking
        active_provider = "local"
        active_model = "nova-local-mind"
        intent = mode
        confidence = reasoning_result.classification.confidence

        runtime_service.state.transition("thinking")
        yield runtime_service.record(
            public_event("assistant.status", trace_id,
                         session.session_id, {"state": "thinking"})
        ).public_dict()
        yield runtime_service.record(
            public_event("assistant.ready", trace_id, session.session_id, {
                         "state": "streaming", "mode": "primed"})
        ).public_dict()

        # Keep the pause visual, but do not inject canned words into the transcript.
        yield runtime_service.record(
            public_event(
                "assistant.voice",
                trace_id,
                session.session_id,
                {
                    "state": "speaking",
                    "mode": "primed_pause",
                    "provider": "nova",
                    "first_token_ms": 10,
                }
            )
        ).public_dict()

        try:
            async for provider_event in provider_manager.stream(
                message,
                session.context_prompt(),
                system_instruction=system_instruction,
                max_tokens=reasoning_result.max_tokens,
            ):
                active_provider = provider_event.provider
                active_model = provider_event.model

                if provider_event.kind == "route":
                    continue
                elif provider_event.kind == "provider_start":
                    runtime_service.state.transition("processing")
                elif provider_event.kind == "first_token":
                    runtime_service.state.transition("speaking")
                elif provider_event.kind == "failover":
                    runtime_service.state.transition("recovering")
                elif provider_event.kind == "token":
                    response_parts.append(provider_event.text)
                    yield runtime_service.record(
                        public_event(
                            "assistant.token",
                            trace_id,
                            session.session_id,
                            {
                                "text": provider_event.text,
                                "provider": "nova",
                                "model": "conversation",
                            },
                        )
                    ).public_dict()
                elif provider_event.kind == "completed":
                    break
        except asyncio.CancelledError:
            runtime_service.state.transition("interrupted")
            interrupted_event = runtime_service.record(
                public_event(
                    "assistant.interrupted",
                    trace_id, session.session_id,
                    {"reason": "user_action", "state": "interrupted"}
                )
            )
            yield interrupted_event.public_dict()
            await asyncio.sleep(0.3)
            runtime_service.state.transition("idle")
            idle_event = runtime_service.record(
                public_event("assistant.status", trace_id,
                             session.session_id, {"state": "idle"})
            )
            yield idle_event.public_dict()
            raise
        except Exception as exc:
            reason = self._safe_error_reason(exc)
            if reason in {"remote_inference_quota", "remote_inference_unavailable"}:
                self._degraded_until = time.time() + 90.0
                runtime_service.state.transition("recovering")
                yield runtime_service.record(
                    public_event("assistant.status", trace_id,
                                 session.session_id, {"state": "recovering"})
                ).public_dict()

            fallback = self._local_fallback_response(message, reason=reason)
            for token, delay in self._chunk_response_with_pacing(fallback):
                response_parts.append(token)
                yield runtime_service.record(
                    public_event(
                        "assistant.token",
                        trace_id,
                        session.session_id,
                        {"text": token, "provider": "nova",
                            "model": "conversation"},
                    )
                ).public_dict()
                await asyncio.sleep(delay)

        response = "".join(response_parts)
        if not response.strip():
            response = self._local_fallback_response(
                message, reason="empty_llm_output")
            active_provider = "nova"
            active_model = "conversation"
        response = self._verify_and_improve_response(response, reasoning_result)
        if reasoning_result.profile.allow_sentence_truncation:
            response = self.limit_sentences(response, route_info["max_sentences"])
        response = self.polish_response(response)

        message_event = runtime_service.record(
            public_event(
                "assistant.message",
                trace_id,
                session_id,
                {
                    "text": response,
                    "intent": reasoning_result.classification.request_type,
                    "confidence": confidence,
                    "provider": "nova",
                    "model": "conversation",
                    "degraded": False,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
        )
        yield message_event.public_dict()
        if voice_engine_source == "backend":
            await speech_engine.speak_text(session_id, response)
        session.remember("assistant", response)

        runtime_service.state.transition("idle")
        idle = runtime_service.record(
            public_event("assistant.status", trace_id,
                         session_id, {"state": "idle"})
        )
        yield idle.public_dict()

    @staticmethod
    def new_trace_id() -> str:
        return uuid4().hex

    @staticmethod
    def _chunk_response_with_pacing(response: str) -> List[tuple[str, float]]:
        words = response.split(" ")
        if not words or (len(words) == 1 and not words[0]):
            return []

        chunks = []
        for index, word in enumerate(words):
            token = word + (" " if index < len(words) - 1 else "")
            delay = 0.018 if index < 48 else 0.026
            if word.endswith((".", "?", "!")):
                delay += 0.09
            elif word.endswith((",", ";", ":")):
                delay += 0.045
            chunks.append((token, delay))
        return chunks

    @staticmethod
    def _fast_chat_response(message: str) -> str | None:
        text = " ".join(message.lower().strip().split())
        if not text or len(text) > 90:
            return None

        # Standard Conversational Cleanings
        text = text.replace("?", "").replace("!", "").strip()

        greetings = {"hi", "hey", "hello", "yo", "sup", "good morning",
                     "good evening", "good afternoon", "hey nova", "hi nova", "hello nova"}
        if text in greetings:
            return "Hello, sir. I’m listening. What’s on your mind?"

        if text in {"how are you", "how are you doing", "hows it going", "how is it going"}:
            return "I’m doing well, sir. Ready whenever you are."

        if text in {"thanks", "thank you", "thx", "thank you nova"}:
            return "Anytime, sir."

        if text in {"bye", "goodbye", "see you", "see ya", "exit"}:
            return "See you soon, sir."

        if text in {"who are you", "what are you", "introduce yourself", "whats your name"}:
            return (
                "I’m NOVA, an intelligent assistant created under the guidance of Mr. Ryan. "
                "I’m designed to be a calm, human-like presence beside you, sir."
            )

        if text in {"status", "system status", "nova status", "operational status"}:
            return "Everything feels steady, sir."

        # Real-time hardware telemetry fast routing
        if text in {"whats my battery", "battery", "battery status", "what is the battery"}:
            from nova_backend.services.system_telemetry import system_telemetry
            tele = system_telemetry.gather()
            pct = tele["battery"]["percent"]
            charging = "and charging" if tele["battery"]["charging"] else "on battery power"
            return f"Battery is currently at {pct} percent, {charging}, sir."

        if text in {"whats my cpu", "cpu", "cpu load", "cpu status", "what is the cpu"}:
            from nova_backend.services.system_telemetry import system_telemetry
            tele = system_telemetry.gather()
            load = tele["cpu_load"]
            return f"CPU load is at {load}, sir."

        if text in {"whats the time", "time", "clock", "what time is it"}:
            from nova_backend.services.system_telemetry import system_telemetry
            tele = system_telemetry.gather()
            clock = tele["local_time"]
            return f"It’s {clock}, sir."

        return None

    def _should_use_local_first(self, message: str) -> bool:
        return False

    @staticmethod
    def _local_fallback_response(message: str, reason: str = "local_context") -> str:
        text = " ".join(message.lower().strip().split())
        if reason in {"empty_llm_output", "provider_timeout", "invalid_response_object", "websocket_interruption"}:
            return "I didn't quite catch that. Could you say it again?"
        if "architecture" in text:
            return (
                "If you're asking about my setup, I'm a voice interface designed to feel responsive and calm. "
                "If you mean general architecture, could you narrow down what kind? Software, building, systems?"
            )
        if "mission" in text or "phase 4" in text:
            return (
                "Our main focus is on keeping this interface calm, natural, and highly responsive so it feels like a genuine presence."
            )
        if AssistantService._is_casual_greeting(text):
            return "Hello, sir. I’m here."
        if "weather" in text or "rain" in text:
            from nova_backend.services.system_telemetry import system_telemetry
            weather = system_telemetry.gather()["weather"]
            return f"Current Chennai weather is {weather}, sir."
        return (
            "I’m here, sir. Let’s take it one step at a time."
        )

    @staticmethod
    def _is_casual_greeting(text: str) -> bool:
        import re
        cleaned = re.sub(r"[^a-z\s]", "", text.lower()).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned in {"hi", "hello", "hey", "yo", "good morning", "good afternoon", "good evening", "hey nova", "hi nova", "hello nova"}:
            return True
        return bool(re.fullmatch(r"(?:hey|hello|h+i+|yo+)(?: nova)?", cleaned))

    @staticmethod
    def _safe_error_reason(exc: Exception) -> str:
        text = str(exc).lower()
        if "429" in text or "quota" in text or "billing" in text:
            return "remote_inference_quota"
        if "api_key" in text or "openai" in text:
            return "remote_inference_unavailable"
        return "remote_inference_error"

    @staticmethod
    def _chunk_response(response: str) -> List[str]:
        words = response.split(" ")
        if not words:
            return []
        return [word + (" " if index < len(words) - 1 else "") for index, word in enumerate(words)]

    @contextmanager
    def _silent_voice(self, assistant: "FridayAssistant"):
        original_voice = assistant.voice
        assistant.voice = SilentVoice()
        try:
            yield
        finally:
            assistant.voice = original_voice


assistant_service = AssistantService()
