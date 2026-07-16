from dataclasses import dataclass
from typing import List

from nova_backend.providers.unified_stream import ProviderName


@dataclass(frozen=True)
class RouteDecision:
    primary: ProviderName
    reason: str
    ordered_providers: List[ProviderName]


class ProviderRouter:
    factual_markers = (
        "latest", "today", "current", "news", "search", "who won",
        "price", "weather", "market", "stock", "recent",
    )
    reasoning_markers = (
        "architect", "design", "analyze", "strategy", "reason", "plan",
        "debug", "build", "complex", "tradeoff",
    )

    def route(self, prompt: str) -> RouteDecision:
        text = " ".join(prompt.lower().strip().split())
        word_count = len(text.split())

        if any(marker in text for marker in self.factual_markers):
            return RouteDecision("openai", "factual_or_search", ["openai", "ollama"])

        if word_count > 80 or any(marker in text for marker in self.reasoning_markers):
            return RouteDecision("openai", "heavy_reasoning", ["openai", "ollama"])

        if word_count <= 18:
            return RouteDecision("ollama", "fast_short_prompt", ["ollama", "openai"])

        return RouteDecision("ollama", "balanced_default", ["ollama", "openai"])
