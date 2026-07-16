import re
from dataclasses import dataclass
from typing import Literal


RequestType = Literal[
    "knowledge",
    "coding",
    "debugging",
    "code_review",
    "architecture",
    "planning",
    "decision_making",
    "research",
    "mathematics",
    "game_development",
    "creative",
    "conversation",
    "project_analysis",
]

DepthEstimate = Literal["shallow", "medium", "deep"]


@dataclass(frozen=True)
class ClassificationResult:
    request_type: RequestType
    confidence: float
    depth: DepthEstimate
    scores: dict[str, float]
    signals: list[str]


class RequestClassifier:
    """Rule-based first-pass classifier for NOVA intelligence routing."""

    CODE_BLOCK_RE = re.compile(r"```|^\s*(def|class|import|from|const|let|var|function)\b", re.MULTILINE)
    STACKTRACE_RE = re.compile(r"\b(traceback|exception|stack trace|syntaxerror|typeerror|referenceerror|segmentation fault)\b", re.I)
    MATH_RE = re.compile(r"([-+]?\d+(?:\.\d+)?\s*[-+*/^%=]\s*[-+]?\d+)|(\b(integral|derivative|differentiate|equation|matrix|limit|probability|calculate|solve)\b)", re.I)

    KEYWORDS: dict[RequestType, tuple[str, ...]] = {
        "project_analysis": (
            "this project", "our code", "nova", "codebase", "backend", "implementation",
            "repo", "repository", "project files", "current code", "existing code",
        ),
        "coding": (
            "write code", "implement", "create function", "build script", "api endpoint",
            "python", "javascript", "typescript", "react", "fastapi", "sql", "algorithm",
            "class", "module", "package",
        ),
        "debugging": (
            "bug", "debug", "fix", "error", "exception", "crash", "failing", "doesn't work",
            "not working", "traceback", "stack trace", "regression", "broken",
        ),
        "code_review": (
            "review this code", "code review", "review my code", "audit this code",
            "find bugs", "security review", "performance review", "pr review",
        ),
        "architecture": (
            "architecture", "system design", "design a system", "distributed", "scalable",
            "microservices", "reliability", "high availability", "database design",
            "platform", "infrastructure",
        ),
        "planning": (
            "plan", "roadmap", "strategy", "steps", "break down", "milestone",
            "project plan", "implementation plan", "how should i approach",
        ),
        "decision_making": (
            "choose", "decide", "decision", "which option", "best option",
            "pros and cons", "tradeoff", "recommend", "should i", "better approach",
        ),
        "research": (
            "latest", "current", "today", "news", "recent", "research", "compare",
            "market", "price", "weather", "who won", "find sources", "look up",
        ),
        "game_development": (
            "snake", "tic tac toe", "connect four", "crossword", "chess", "memory game",
            "puzzle game", "platformer", "game loop", "collision", "score", "playable game",
        ),
        "creative": (
            "write a story", "poem", "creative", "brainstorm", "name ideas", "tagline",
            "script", "dialogue", "lyrics", "worldbuild",
        ),
        "knowledge": (
            "what is", "why", "how does", "explain", "define", "tell me about",
            "difference between", "can you explain",
        ),
        "conversation": (
            "hello", "hi", "hey", "thanks", "thank you", "ok", "yes", "no",
            "how are you", "good morning", "good evening",
        ),
        "mathematics": (),
    }

    PRIORITY: tuple[RequestType, ...] = (
        "project_analysis",
        "code_review",
        "debugging",
        "game_development",
        "architecture",
        "coding",
        "mathematics",
        "research",
        "decision_making",
        "planning",
        "creative",
        "knowledge",
        "conversation",
    )

    def classify(self, message: str) -> ClassificationResult:
        text = " ".join(message.strip().split())
        lowered = text.lower()
        scores = {request_type: 0.0 for request_type in self.PRIORITY}
        signals: list[str] = []

        if not lowered:
            return ClassificationResult("conversation", 0.1, "shallow", scores, ["empty"])

        for request_type, keywords in self.KEYWORDS.items():
            for keyword in keywords:
                if keyword in lowered:
                    scores[request_type] += 1.0
                    signals.append(f"{request_type}:{keyword}")

        if self.CODE_BLOCK_RE.search(message):
            scores["coding"] += 2.0
            signals.append("structure:code_detected")

        if self.STACKTRACE_RE.search(message):
            scores["debugging"] += 2.5
            signals.append("structure:error_trace_detected")

        if self.MATH_RE.search(message):
            scores["mathematics"] += 2.0
            signals.append("structure:math_detected")

        if self._project_reference_detected(lowered):
            scores["project_analysis"] += 2.5
            signals.append("intent:project_reference")

        if "review" in lowered and self.CODE_BLOCK_RE.search(message):
            scores["code_review"] += 2.0
            signals.append("structure:review_plus_code")

        if "game" in lowered and any(word in lowered for word in ("build", "create", "make", "implement")):
            scores["game_development"] += 1.5
            signals.append("intent:game_build")

        if lowered.endswith("?") and max(scores.values()) < 1.0:
            scores["knowledge"] += 0.8
            signals.append("structure:question_mark")

        if len(lowered.split()) <= 3 and max(scores.values()) <= 1.0:
            scores["conversation"] += 1.2
            signals.append("structure:short_conversation")

        request_type = self._winner(scores)
        confidence = self._confidence(scores, request_type)
        depth = self.estimate_depth(message, request_type, scores)
        return ClassificationResult(request_type, confidence, depth, scores, signals[:10])

    def estimate_depth(
        self,
        message: str,
        request_type: RequestType,
        scores: dict[str, float] | None = None,
    ) -> DepthEstimate:
        lowered = message.lower()
        word_count = len(lowered.split())
        deep_markers = (
            "distributed", "architecture", "platform", "production", "scalable",
            "security", "performance", "large codebase", "end to end", "complete",
            "advanced", "system design", "tradeoff",
        )
        medium_markers = (
            "bug", "python", "javascript", "code", "debug", "plan", "algorithm",
            "compare", "explain", "implement", "review",
        )

        if request_type == "conversation" and word_count <= 5:
            return "shallow"
        if request_type in {"architecture", "code_review", "game_development", "project_analysis"}:
            return "deep"
        if request_type in {"coding", "debugging"} and (
            word_count > 45 or self.CODE_BLOCK_RE.search(message) or self.STACKTRACE_RE.search(message)
        ):
            return "deep"
        if any(marker in lowered for marker in deep_markers) or word_count > 80:
            return "deep"
        if request_type in {"coding", "debugging", "planning", "research", "mathematics", "decision_making"}:
            return "medium"
        if any(marker in lowered for marker in medium_markers) or word_count > 18:
            return "medium"
        return "shallow"

    def _winner(self, scores: dict[str, float]) -> RequestType:
        best = "conversation"
        best_score = scores.get(best, 0.0)
        for request_type in self.PRIORITY:
            score = scores.get(request_type, 0.0)
            if score > best_score:
                best = request_type
                best_score = score
        if best_score == 0.0:
            return "knowledge"
        return best

    @staticmethod
    def _project_reference_detected(text: str) -> bool:
        markers = (
            "this project", "our code", "codebase", "backend", "architecture",
            "implementation", "repo", "repository", "project_a",
        )
        if any(marker in text for marker in markers):
            return True
        return "nova" in text and any(
            word in text for word in ("code", "backend", "architecture", "implementation", "project", "service")
        )

    @staticmethod
    def _confidence(scores: dict[str, float], request_type: RequestType) -> float:
        best = scores.get(request_type, 0.0)
        total = sum(max(score, 0.0) for score in scores.values())
        if total <= 0:
            return 0.45
        margin = best - max((score for key, score in scores.items() if key != request_type), default=0.0)
        raw = 0.45 + min(0.4, best / 8.0) + min(0.15, max(0.0, margin) / 6.0)
        return round(max(0.45, min(raw, 0.98)), 2)
