from contextlib import asynccontextmanager
import asyncio
import threading
import time
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from starlette.responses import Response

from config import config
from nova_backend.logging_config import configure_logging, get_logger
from nova_backend.providers.provider_manager import provider_manager
from nova_backend.schemas import ChatRequest, ChatResponse, HealthResponse
from nova_backend.security import require_admin
from nova_backend.runtime.service import runtime_service
from nova_backend.services.assistant_service import assistant_service
from nova_backend.services.speech_engine import speech_engine

print("[PHASE_4_8_6_BACKEND_ACTIVE]")


def open_browser():
    import webbrowser
    time.sleep(1.0)
    try:
        webbrowser.open("http://localhost:3000")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger = get_logger(__name__)
    logger.info("starting NOVA OS backend")
    runtime_service.state.transition("booting")
    threading.Thread(target=open_browser, daemon=True).start()
    await assistant_service.initialize()
    runtime_service.state.transition("ready" if assistant_service.status()[
                                     "initialized"] else "idle")
    yield
    runtime_service.state.transition("shutdown")
    logger.info("stopping NOVA OS backend")


app = FastAPI(
    title=config.app_name,
    version="0.2.0",
    description="NOVA OS backend API wrapping the existing Friday intelligence runtime.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_lifecycle(request: Request, call_next) -> Response:
    trace_id = request.headers.get(
        "x-trace-id") or assistant_service.new_trace_id()
    logger = get_logger(__name__, trace_id)
    started = time.perf_counter()

    logger.info("request started method=%s path=%s",
                request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request failed method=%s path=%s",
                         request.method, request.url.path)
        raise

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["x-trace-id"] = trace_id
    response.headers["x-response-time-ms"] = str(elapsed_ms)
    logger.info(
        "request completed method=%s path=%s status=%s latency_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    services = assistant_service.status()
    services["runtime"] = runtime_service.state.snapshot()
    services["providers"] = await provider_manager.status()
    status = "ok" if services["openai_configured"] else "degraded"
    return HealthResponse(
        status=status,
        app=config.app_name,
        environment=config.environment,
        services=services,
    )


@app.get("/api/health", response_model=HealthResponse)
async def api_health() -> HealthResponse:
    return await health()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    trace_id = assistant_service.new_trace_id()
    session = runtime_service.sessions.get_or_create(
        request.session_id, request.user_id)
    logger = get_logger(__name__, trace_id)
    logger.info("chat turn received session_id=%s", session.session_id)

    try:
        result = await assistant_service.run_turn(
            request.message,
            trace_id,
            session.session_id,
            request.user_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatResponse(
        trace_id=trace_id,
        session_id=result["session_id"],
        response=result["response"],
        intent=result["intent"],
        confidence=result["confidence"],
        events=result["public_events"],
    )


# ============================================================
# PHASE 4.8.6 — WEBSOCKET STATE MANAGEMENT
# ============================================================

active_streaming_tasks: dict[str, asyncio.Task] = {}
active_websockets: dict[str, WebSocket] = {}
session_voice_sources: dict[str, str] = {}

# BOOT STATE MACHINE
# Tracks boot greeting across the global process lifetime.
# We only ever greet once per backend process start.
# Reconnects from the same browser session are debounced by session_id.
_boot_lock = asyncio.Lock()
_greeted_sessions: set[str] = set()     # Per-session greeting deduplication
_system_sleeping = False


def is_wake_phrase(message: str) -> bool:
    import re
    cleaned = re.sub(r"[^\w\s]", "", message.lower().strip())
    cleaned = " ".join(cleaned.split())
    wake_phrases = {
        "hey nova", "nova", "wake up nova", "time to work nova",
        "up there nova", "you there nova"
    }
    if cleaned in wake_phrases:
        return True
    for wp in wake_phrases:
        if cleaned == wp or cleaned.startswith(wp) or cleaned.endswith(wp):
            return True
    return False


async def safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    """Send to a websocket only while it is open; never crash on closed sockets."""
    if (websocket.client_state != WebSocketState.CONNECTED or
            websocket.application_state != WebSocketState.CONNECTED):
        return False
    try:
        await websocket.send_json(payload)
        return True
    except (RuntimeError, WebSocketDisconnect):
        return False


async def cancel_session_stream(session_id: str) -> None:
    task = active_streaming_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    # Only the active owner may stop speech. Browser-owned sessions must not
    # touch backend speech during passive websocket recovery.
    if session_voice_sources.get(session_id) == "backend":
        await speech_engine.stop(session_id)


async def cancel_session_generation(session_id: str) -> None:
    task = active_streaming_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


async def stream_canned_response(
    websocket: WebSocket,
    trace_id: str,
    session: Any,
    text: str,
    intent: str,
    voice_engine_source: str,
    next_state: str = "idle"
):
    runtime_service.state.transition("speaking")
    await safe_send_json(websocket, {
        "type": "assistant.status",
        "trace_id": trace_id,
        "session_id": session.session_id,
        "payload": {"state": "speaking"}
    })

    # Backend speech ONLY when explicitly requested and not browser mode
    if voice_engine_source == "backend":
        await speech_engine.speak_text(session.session_id, text)

    response_parts = []
    for token, delay in assistant_service._chunk_response_with_pacing(text):
        response_parts.append(token)
        if not await safe_send_json(websocket, {
            "type": "assistant.token",
            "trace_id": trace_id,
            "session_id": session.session_id,
            "payload": {
                "text": token,
                "provider": "nova",
                "model": "conversation"
            }
        }):
            break
        await asyncio.sleep(delay)

    await safe_send_json(websocket, {
        "type": "assistant.message",
        "trace_id": trace_id,
        "session_id": session.session_id,
        "payload": {
            "text": text,
            "intent": intent,
            "confidence": 1.0,
            "provider": "nova",
            "model": "conversation",
            "degraded": False,
            "latency_ms": 10
        }
    })

    runtime_service.state.transition(next_state)
    await safe_send_json(websocket, {
        "type": "assistant.status",
        "trace_id": trace_id,
        "session_id": session.session_id,
        "payload": {"state": next_state}
    })


@app.websocket("/ws/assistant")
async def assistant_websocket(websocket: WebSocket):
    global _system_sleeping

    await websocket.accept()
    trace_id = assistant_service.new_trace_id()
    logger = get_logger(__name__, trace_id)
    logger.info("websocket connected")

    from nova_backend.services.voice_processor import voice_processor

    session_id_ref = None

    try:
        while True:
            payload = await websocket.receive_json()
            user_id = str(payload.get("user_id", "user_default"))
            session = runtime_service.sessions.get_or_create(
                payload.get("session_id"), user_id)
            session_id_ref = session.session_id

            # Stale socket cleanup: if there is already a different socket for
            # this session, cancel its streaming work before replacing it.
            previous_socket = active_websockets.get(session.session_id)
            if previous_socket is not None and previous_socket is not websocket:
                await cancel_session_generation(session.session_id)
            active_websockets[session.session_id] = websocket

            msg_type = payload.get("type")

            # ------------------------------------------------------------------
            # HEARTBEAT PING/PONG — keeps connection alive, detects dead sockets
            # ------------------------------------------------------------------
            if msg_type == "ping":
                await safe_send_json(websocket, {
                    "type": "pong",
                    "timestamp": time.time()
                })
                continue

            # ------------------------------------------------------------------
            # BOOT SEQUENCE — PRIORITY 1
            # Greeting fires exactly once per process lifetime.
            # Reconnects from the same session are debounced.
            # ------------------------------------------------------------------
            if msg_type == "user.boot":
                personality = "friday"
                voice_engine_source = payload.get(
                    "voice_engine_source", "browser")
                session_voice_sources[session.session_id] = voice_engine_source
                logger.info("Boot event received. source=%s session=%s",
                            voice_engine_source, session.session_id)

                if _system_sleeping:
                    logger.info(
                        "[BOOT] System sleeping — suppressing greeting.")
                    await safe_send_json(websocket, {
                        "type": "assistant.status",
                        "trace_id": assistant_service.new_trace_id(),
                        "session_id": session.session_id,
                        "payload": {"state": "sleeping"}
                    })
                    continue

                # Per-session deduplication (handles browser refresh correctly)
                if session.session_id in _greeted_sessions:
                    logger.info(
                        "[BOOT] Session already greeted — suppressing duplicate.")
                    await safe_send_json(websocket, {
                        "type": "assistant.status",
                        "trace_id": assistant_service.new_trace_id(),
                        "session_id": session.session_id,
                        "payload": {"state": "idle"}
                    })
                    continue

                # Global boot mutex — only one boot greeting fires at a time
                async with _boot_lock:
                    if session.session_id in _greeted_sessions:
                        # Lost the race inside the lock
                        await safe_send_json(websocket, {
                            "type": "assistant.status",
                            "trace_id": assistant_service.new_trace_id(),
                            "session_id": session.session_id,
                            "payload": {"state": "idle"}
                        })
                        continue

                    # Mark session greeted immediately to prevent re-entry
                    _greeted_sessions.add(session.session_id)

                # Voice lock confirmation log
                if voice_engine_source == "browser":
                    print("[VOICE READY]")
                    print("[FEMALE VOICE LOCK CONFIRMED]")
                    logger.info("[VOICE READY]")
                    logger.info("[FEMALE VOICE LOCK CONFIRMED]")

                if voice_engine_source == "backend":
                    speech_engine.set_personality(personality)

                from nova_backend.services.response_modes import response_modes
                greeting = response_modes.compose_canned_boot_greeting(
                    personality)

                print("[BOOT GREETING START]")
                logger.info("[BOOT GREETING START]")

                trace_id = assistant_service.new_trace_id()
                runtime_service.state.transition("speaking")
                if not await safe_send_json(websocket, {
                    "type": "assistant.status",
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "payload": {"state": "speaking"}
                }):
                    break

                # Backend speech only when explicitly requested
                if voice_engine_source == "backend":
                    await speech_engine.speak_text(session.session_id, greeting)

                response_parts = []
                for token, delay in assistant_service._chunk_response_with_pacing(greeting):
                    response_parts.append(token)
                    if not await safe_send_json(websocket, {
                        "type": "assistant.token",
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "payload": {
                            "text": token,
                            "provider": "nova",
                            "model": "conversation"
                        }
                    }):
                        break
                    await asyncio.sleep(delay)

                if not await safe_send_json(websocket, {
                    "type": "assistant.message",
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "payload": {
                        "text": greeting,
                        "intent": "system_boot",
                        "confidence": 1.0,
                        "provider": "nova",
                        "model": "conversation",
                        "degraded": False,
                        "latency_ms": 10
                    }
                }):
                    break

                print("[BOOT GREETING COMPLETE]")
                logger.info("[BOOT GREETING COMPLETE]")

                runtime_service.state.transition("idle")
                await safe_send_json(websocket, {
                    "type": "assistant.status",
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "payload": {"state": "idle"}
                })
                continue

            # ------------------------------------------------------------------
            # FRONTEND READY EVENT — signals full hydration complete
            # ------------------------------------------------------------------
            elif msg_type == "frontend.ready":
                logger.info("[FRONTEND READY] session=%s", session.session_id)
                await safe_send_json(websocket, {
                    "type": "assistant.status",
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "payload": {"state": runtime_service.state.state}
                })
                continue

            # ------------------------------------------------------------------
            # VOICE READY EVENT — browser voice engine initialized
            # ------------------------------------------------------------------
            elif msg_type == "voice.ready":
                logger.info(
                    "[VOICE READY — CLIENT CONFIRMED] session=%s voice=%s",
                    session.session_id,
                    payload.get("locked_voice", "unknown"),
                )
                continue

            # ------------------------------------------------------------------
            # EXPLICIT INTERRUPTION
            # ------------------------------------------------------------------
            elif msg_type == "user.interrupt":
                logger.info(
                    "Interruption signal received session=%s", session.session_id)
                await cancel_session_stream(session.session_id)
                runtime_service.state.transition("interrupted")
                if not await safe_send_json(websocket, {
                    "type": "assistant.interrupted",
                    "event_id": assistant_service.new_trace_id(),
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "timestamp": time.time(),
                    "payload": {"reason": "user_action", "state": "interrupted"}
                }):
                    break
                runtime_service.state.transition("idle")
                await safe_send_json(websocket, {
                    "type": "assistant.status",
                    "event_id": assistant_service.new_trace_id(),
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "timestamp": time.time(),
                    "payload": {"state": "idle"}
                })
                continue

            # ------------------------------------------------------------------
            # TRANSCRIPT RELAY
            # ------------------------------------------------------------------
            elif msg_type == "user.transcript":
                transcript = str(payload.get("transcript", "")).strip()
                await safe_send_json(websocket, {
                    "type": "assistant.transcript",
                    "event_id": assistant_service.new_trace_id(),
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "timestamp": time.time(),
                    "payload": {
                        "text": transcript,
                        "final": bool(payload.get("final", False)),
                        "wake": bool(payload.get("wake", False)),
                    },
                })
                continue

            # ------------------------------------------------------------------
            # MICROPHONE AUDIO FRAMES (VAD)
            # ------------------------------------------------------------------
            elif msg_type == "user.audio":
                audio_base64 = payload.get("audio", "")
                result = voice_processor.ingest_audio_frame(audio_base64)

                if result.get("interrupted") or (result.get("user_speaking") and session.session_id in active_streaming_tasks):
                    logger.info(
                        "Voice activity interruption detected session=%s", session.session_id)
                    await cancel_session_stream(session.session_id)
                    runtime_service.state.transition("interrupted")
                    if not await safe_send_json(websocket, {
                        "type": "assistant.interrupted",
                        "event_id": assistant_service.new_trace_id(),
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "timestamp": time.time(),
                        "payload": {"reason": "voice_activity", "state": "interrupted"}
                    }):
                        break
                    runtime_service.state.transition("idle")
                    await safe_send_json(websocket, {
                        "type": "assistant.status",
                        "event_id": assistant_service.new_trace_id(),
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "timestamp": time.time(),
                        "payload": {"state": "idle"}
                    })

                if result.get("state_changed"):
                    if result["user_speaking"]:
                        runtime_service.state.transition("listening")
                        if not await safe_send_json(websocket, {
                            "type": "assistant.listening",
                            "trace_id": trace_id,
                            "session_id": session.session_id,
                            "payload": {"state": "listening"}
                        }):
                            break
                    else:
                        runtime_service.state.transition("idle")
                        if not await safe_send_json(websocket, {
                            "type": "assistant.status",
                            "trace_id": trace_id,
                            "session_id": session.session_id,
                            "payload": {"state": "idle"}
                        }):
                            break

                if not await safe_send_json(websocket, {
                    "type": "assistant.telemetry",
                    "trace_id": trace_id,
                    "session_id": session.session_id,
                    "payload": {
                        "energy": result.get("energy", 0.0),
                        "user_speaking": result.get("user_speaking", False)
                    }
                }):
                    break
                continue

            # ------------------------------------------------------------------
            # NORMAL TEXT MESSAGE TURN
            # ------------------------------------------------------------------
            else:
                message = str(payload.get("message", "")).strip()
                if not message:
                    await safe_send_json(
                        websocket,
                        {
                            "type": "assistant.error",
                            "trace_id": trace_id,
                            "session_id": session.session_id,
                            "payload": {"message": "Message is required."},
                        }
                    )
                    continue

                trace_id = assistant_service.new_trace_id()
                await cancel_session_stream(session.session_id)

                personality = "friday"
                voice_engine_source = payload.get(
                    "voice_engine_source", "browser")
                session_voice_sources[session.session_id] = voice_engine_source

                import random

                # Sleep check
                if _system_sleeping:
                    if is_wake_phrase(message):
                        _system_sleeping = False
                        wake_responses = [
                            "Hello, sir. I’m here.",
                            "I’m listening, sir.",
                            "Good to hear you, sir."
                        ]
                        wake_text = random.choice(wake_responses)
                        await stream_canned_response(websocket, trace_id, session, wake_text, "wake_up", voice_engine_source, "idle")
                    else:
                        logger.info("System sleeping — ignoring message.")
                        await safe_send_json(websocket, {
                            "type": "assistant.status",
                            "trace_id": trace_id,
                            "session_id": session.session_id,
                            "payload": {"state": "sleeping"}
                        })
                    continue

                # Sleep command
                cleaned_msg = message.lower().strip().rstrip(".!?")
                if cleaned_msg in {"stop", "pause", "quiet", "be quiet"}:
                    await cancel_session_stream(session.session_id)
                    runtime_service.state.transition("idle")
                    await safe_send_json(websocket, {
                        "type": "assistant.status",
                        "trace_id": trace_id,
                        "session_id": session.session_id,
                        "payload": {"state": "idle"}
                    })
                    continue

                if cleaned_msg in {"sleep", "shutdown", "goodnight", "stand by"}:
                    _system_sleeping = True
                    sleep_responses = [
                        "Going quiet for now, sir. Let me know when you need me.",
                        "Going quiet, sir. I’ll be here.",
                        "Going to sleep, sir. Let me know when you're ready to begin again."
                    ]
                    sleep_text = random.choice(sleep_responses)
                    await stream_canned_response(websocket, trace_id, session, sleep_text, "standby", voice_engine_source, "sleeping")
                    continue

                if voice_engine_source == "backend":
                    speech_engine.set_personality(personality)

                async def run_stream(t_id, s_id, u_id, msg, pers, src):
                    try:
                        async for event in assistant_service.stream_turn(msg, t_id, s_id, u_id, voice_personality=pers, voice_engine_source=src):
                            if active_websockets.get(s_id) is not websocket:
                                break
                            if not await safe_send_json(websocket, event):
                                break
                    except asyncio.CancelledError:
                        logger.info(
                            "Streaming task cancelled session=%s", s_id)
                        runtime_service.state.transition("idle")
                    except Exception as e:
                        logger.exception(
                            "Error in streaming task: %s", e)
                        runtime_service.state.transition("idle")
                    finally:
                        if active_streaming_tasks.get(s_id) is asyncio.current_task():
                            active_streaming_tasks.pop(s_id, None)

                task = asyncio.create_task(run_stream(
                    trace_id, session.session_id, user_id, message, personality, voice_engine_source))
                active_streaming_tasks[session.session_id] = task

    except WebSocketDisconnect:
        logger.info("websocket disconnected")
    finally:
        if session_id_ref:
            if active_websockets.get(session_id_ref) is websocket:
                active_websockets.pop(session_id_ref, None)
            await cancel_session_generation(session_id_ref)


@app.get("/api/runtime")
async def runtime_snapshot(session_id: str | None = None):
    snapshot = runtime_service.snapshot(session_id)
    return {
        "assistant": snapshot["assistant"],
        "session": snapshot["session"],
    }


@app.get("/admin/health", dependencies=[Depends(require_admin)])
async def admin_health():
    return {
        "status": "ok",
        "runtime": assistant_service.status(),
        "private_observability": {
            "logs": "enabled",
            "reasoning_traces": "planned",
            "tool_traces": "planned",
            "memory_diagnostics": "planned",
        },
    }


@app.get("/admin/telemetry/events", dependencies=[Depends(require_admin)])
async def admin_events(limit: int = 100, trace_id: str | None = None):
    return {
        "events": runtime_service.telemetry.recent(limit=limit, trace_id=trace_id),
    }


@app.get("/admin/runtime", dependencies=[Depends(require_admin)])
async def admin_runtime(session_id: str | None = None):
    return runtime_service.snapshot(session_id)


@app.get("/admin/providers", dependencies=[Depends(require_admin)])
async def admin_providers():
    return await provider_manager.status()
