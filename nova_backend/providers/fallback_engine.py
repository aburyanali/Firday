import ast
import operator
import random
import re
from dataclasses import dataclass, field
from typing import AsyncIterator

from nova_backend.providers.local_stream_adapter import paced_stream
from nova_backend.providers.unified_stream import BaseProvider, ProviderChunk


@dataclass
class LocalMind:
    facts: dict[str, str] = field(default_factory=dict)
    recent_topics: list[str] = field(default_factory=list)

    def respond(self, prompt: str) -> str:
        context, message = self._split_context(prompt)
        text = " ".join(message.lower().strip().split())
        if not text:
            return "I’m listening, sir. Take your time."

        stored = self._store_fact(text)
        if stored:
            return stored

        recalled = self._recall_fact(text)
        if recalled:
            return recalled

        math_answer = self._solve_math(text)
        if math_answer:
            return math_answer

        self._remember_topic(text)

        if self._is_casual_greeting(text):
            return random.choice(
                [
                    "Hello, sir. I’m here. What are we working on?",
                    "Hello, sir. What’s on your mind?",
                    "Hello, sir. Still working?",
                    "Hello, sir. You’re up late. What are we tackling tonight?",
                ]
            )

        if "how are you" in text:
            return random.choice(["I’m doing well, sir. Ready whenever you are.", "Doing alright, sir. Calm and focused.", "I’m here, sir, and I’m doing well."])

        if any(phrase in text for phrase in ("who are you", "what are you", "who made you", "who created you", "who built you")):
            return (
                "I’m NOVA, an intelligent assistant created under the guidance of Mr. Ryan. "
                "I’m designed to be a calm, human-like presence beside you, not a flashy cinematic AI, sir."
            )

        if "status" in text:
            return "Everything feels steady, sir. I’m ready when you are."

        if any(word in text for word in ("sad", "stressed", "tired", "worried", "anxious")):
            return "I hear you, sir. We can slow the pace, take a breath, and handle one steady step at a time."

        known_answer = self._known_explanation(text)
        if known_answer:
            return known_answer

        if any(word in text for word in ("plan", "strategy", "approach", "debug", "build", "fix")):
            topic = self._topic_from(text)
            return f"For {topic}, sir, I’d start by narrowing the problem, checking the current behavior, then changing one thing at a time."

        if any(word in text for word in ("explain", "why", "how")):
            topic = self._topic_from(text)
            return self._general_explanation(topic)

        if "?" in message:
            topic = self._topic_from(text)
            return self._general_explanation(topic)

        topic = self._topic_from(text)
        return self._general_explanation(topic)

    @staticmethod
    def _is_casual_greeting(text: str) -> bool:
        cleaned = re.sub(r"[^a-z\s]", "", text.lower()).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned in {"hi", "hello", "hey", "yo", "good morning", "good afternoon", "good evening", "hey nova", "hi nova", "hello nova"}:
            return True
        return bool(re.fullmatch(r"(?:hey|hello|h+i+|yo+)(?: nova)?", cleaned))

    def _split_context(self, prompt: str) -> tuple[str, str]:
        marker = "Current user message:"
        if marker not in prompt:
            return "", prompt
        context, message = prompt.rsplit(marker, 1)
        return context.strip(), message.strip()

    def _store_fact(self, text: str) -> str | None:
        match = re.search(r"\b(?:remember|note|save)\s+(?:that\s+)?(.+)", text)
        if not match:
            match = re.search(r"\bmy\s+([a-z][a-z0-9 _-]{1,40})\s+is\s+(.+)", text)
        if not match:
            return None

        if len(match.groups()) == 2:
            key, value = match.group(1).strip(), match.group(2).strip()
        else:
            raw = match.group(1).strip()
            fact = re.search(r"\bmy\s+([a-z][a-z0-9 _-]{1,40})\s+is\s+(.+)", raw)
            if fact:
                key, value = fact.group(1).strip(), fact.group(2).strip()
            else:
                key, value = self._topic_from(raw), raw
        self.facts[key] = value.rstrip(".")
        return f"I'll remember that: {key} is {self.facts[key]}."

    def _recall_fact(self, text: str) -> str | None:
        if not any(phrase in text for phrase in ("what is my", "what's my", "remember", "do you know my", "recall")):
            return None
        for key, value in self.facts.items():
            if key in text:
                return f"You told me your {key} is {value}."
        if self.facts:
            known = ", ".join(sorted(self.facts.keys())[:4])
            return f"I remember a few things: {known}. Which one do you mean?"
        return "I don’t have that stored yet, sir. Tell me once and I’ll remember it for this session."

    @staticmethod
    def _known_explanation(text: str) -> str | None:
        if "hello world" in text and "python" in text:
            return "Here’s the Python version, sir:\n\n```python\nprint(\"Hello, world!\")\n```"
        if "black hole" in text or "black holes" in text:
            return (
                "A black hole is a place where gravity is so strong that even light can’t escape. "
                "Most form when very massive stars collapse, squeezing a huge amount of matter into an extremely small region, sir."
            )
        if "gravity" in text:
            return (
                "Gravity is caused by mass and energy bending spacetime, sir. "
                "Objects move along those curves, which is why planets orbit stars and things fall toward Earth."
            )
        if "recursion" in text:
            return (
                "Recursion is when a function solves a problem by calling itself on a smaller version of the same problem, sir. "
                "The key is a base case that stops the calls, otherwise it keeps going forever."
            )
        if "voice architecture" in text or ("voice" in text and "architecture" in text):
            return (
                "A strong AI voice architecture has a capture layer, streaming speech-to-text, an intent and reasoning layer, low-latency answer delivery, "
                "text-to-speech, and strict interruption handling, sir. The important parts are latency, clear turn control, memory boundaries, and graceful recovery."
            )
        if "machine learning" in text or re.search(r"\bml\b", text):
            return (
                "Machine learning is a field where programs learn from data to make predictions or decisions without being explicitly programmed for every rule, sir. "
                "It powers things like recommendations, image recognition, translation, fraud detection, and self-driving systems."
            )
        if "llm" in text or "large language model" in text:
            return (
                "LLMs are neural networks trained to predict and generate language from patterns in huge text datasets, sir. "
                "They learn statistical structure well enough to write, explain, summarize, code, and reason through many tasks."
            )
        if "loneliness" in text or "lonely" in text:
            return (
                "Loneliness is not just being alone, sir. It’s the feeling that the connection you need is missing, even if people are nearby."
            )
        if "python" in text and "code" in text:
            return "Share the code and the error or behavior you’re seeing, sir. I’ll walk through it clearly."
        if "app idea" in text or ("build" in text and "app" in text):
            return (
                "A strong app idea, sir: a personal study cockpit that turns notes, tasks, and deadlines into one calm daily plan. "
                "Start with notes, task capture, reminders, and a simple dashboard, then add AI summaries once the core flow feels solid."
            )
        if "photosynthesis" in text:
            return (
                "Photosynthesis is how plants turn sunlight, water, and carbon dioxide into sugar for energy, sir. "
                "Oxygen is released as a byproduct, which is why plants are so important to life on Earth."
            )
        return None

    @staticmethod
    def _general_explanation(topic: str) -> str:
        if topic == "that":
            return "I don’t want to fake an answer, sir. Send that once more and I’ll handle it cleanly."
        return (
            f"I don’t want to give you a shallow answer on {topic}, sir. Send it once more and I’ll handle it properly."
        )

    def _solve_math(self, text: str) -> str | None:
        expression = text
        expression = expression.replace("plus", "+").replace("minus", "-")
        expression = expression.replace("times", "*").replace("multiplied by", "*")
        expression = expression.replace("divided by", "/").replace("over", "/")
        match = re.search(r"([-+*/().\d\s]{3,})", expression)
        if not match or not any(op in match.group(1) for op in "+-*/"):
            return None
        try:
            result = _safe_eval(match.group(1).strip())
            rendered = int(result) if float(result).is_integer() else round(float(result), 6)
            return f"{rendered}."
        except Exception:
            return None

    def _remember_topic(self, text: str) -> None:
        topic = self._topic_from(text)
        if topic and topic not in self.recent_topics:
            self.recent_topics.append(topic)
        self.recent_topics = self.recent_topics[-6:]

    def _topic_from(self, text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s-]", " ", text)
        words = [word for word in cleaned.split() if word not in _STOP_WORDS]
        return " ".join(words[:6]) or "that"

    def _context_hint(self, context: str) -> str:
        for line in reversed(context.splitlines()):
            if line.startswith("User:"):
                return self._topic_from(line[5:].lower())
        return self.recent_topics[-1] if self.recent_topics else ""


_STOP_WORDS = {
    "a", "an", "and", "are", "be", "can", "do", "for", "i", "in", "is", "it", "me",
    "my", "of", "on", "or", "please", "should", "that", "the", "this", "to", "we",
    "what", "with", "you",
}

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expression: str) -> float:
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        raise ValueError("unsupported expression")

    return walk(ast.parse(expression, mode="eval"))


class LocalFallbackProvider(BaseProvider):
    name = "local"
    model = "nova-local-mind"

    def __init__(self) -> None:
        self.mind = LocalMind()

    async def stream(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        async for chunk in paced_stream(self.mind.respond(prompt), self.name, self.model):
            yield chunk


class EmergencyProvider(LocalFallbackProvider):
    name = "emergency"
    model = "nova-emergency-mind"
