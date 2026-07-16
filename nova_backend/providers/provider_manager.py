import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List

from config import config
from nova_backend.providers.fallback_engine import EmergencyProvider, LocalFallbackProvider
from nova_backend.providers.ollama_provider import OllamaProvider
from nova_backend.providers.openai_provider import OpenAIProvider
from nova_backend.providers.perplexity_provider import PerplexityProvider
from nova_backend.providers.provider_router import ProviderRouter
from nova_backend.providers.unified_stream import BaseProvider, ProviderError, ProviderName


@dataclass
class ProviderReliability:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_first_token_ms: float = 0.0
    last_error: str | None = None

    @property
    def score(self) -> float:
        if self.attempts == 0:
            return 1.0
        return round(max(0.0, min(1.0, self.successes / self.attempts)), 3)

    @property
    def avg_first_token_ms(self) -> float | None:
        if self.successes == 0:
            return None
        return round(self.total_first_token_ms / self.successes, 2)


@dataclass(frozen=True)
class ProviderStreamEvent:
    kind: str
    provider: ProviderName
    model: str
    text: str = ""
    reason: str = ""
    latency_ms: float | None = None
    attempted: List[ProviderName] = field(default_factory=list)


class ProviderManager:
    def __init__(self) -> None:
        self.router = ProviderRouter()
        self.providers: Dict[ProviderName, BaseProvider] = {
            "openai": OpenAIProvider(),
            "perplexity": PerplexityProvider(),
            "ollama": OllamaProvider(),
            "local": LocalFallbackProvider(),
            "emergency": EmergencyProvider(),
        }
        self.reliability: Dict[ProviderName, ProviderReliability] = {
            name: ProviderReliability() for name in self.providers
        }

    async def stream(
        self,
        prompt: str,
        context: str = "",
        system_instruction: str = "",
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        decision = self.router.route(prompt)
        attempted: List[ProviderName] = []
        yield ProviderStreamEvent("route", decision.primary, self.providers[decision.primary].model, reason=decision.reason)
        provider_prompt = self._with_context(prompt, context)

        for provider_name in decision.ordered_providers:
            provider = self.providers[provider_name]
            attempted.append(provider_name)
            stats = self.reliability[provider_name]
            stats.attempts += 1

            if provider_name != "ollama" and not await provider.is_available():
                stats.failures += 1
                stats.last_error = "not_available"
                yield ProviderStreamEvent("failover", provider_name, provider.model, reason="not_available", attempted=attempted.copy())
                continue

            started = time.perf_counter()
            yield ProviderStreamEvent("provider_start", provider_name, provider.model, reason=decision.reason, attempted=attempted.copy())

            try:
                stream = provider.stream(
                    provider_prompt,
                    system_instruction=system_instruction,
                    max_tokens=max_tokens,
                )
                first_chunk = await asyncio.wait_for(
                    anext(stream),
                    timeout=8.0 if provider_name == "ollama" else config.provider_first_token_timeout_seconds,
                )
                first_token_ms = round((time.perf_counter() - started) * 1000, 2)
                stats.successes += 1
                stats.total_first_token_ms += first_token_ms
                yield ProviderStreamEvent("first_token", provider_name, provider.model, text=first_chunk.text, latency_ms=first_token_ms, attempted=attempted.copy())
                if first_chunk.text:
                    yield ProviderStreamEvent("token", provider_name, provider.model, text=first_chunk.text, latency_ms=first_token_ms, attempted=attempted.copy())

                async for chunk in stream:
                    if chunk.text:
                        yield ProviderStreamEvent("token", provider_name, provider.model, text=chunk.text, attempted=attempted.copy())

                yield ProviderStreamEvent("completed", provider_name, provider.model, attempted=attempted.copy())
                return
            except (asyncio.TimeoutError, ProviderError, Exception) as exc:
                stats.failures += 1
                reason = exc.reason if isinstance(exc, ProviderError) else "timeout" if isinstance(exc, asyncio.TimeoutError) else "provider_error"
                stats.last_error = reason
                yield ProviderStreamEvent("failover", provider_name, provider.model, reason=reason, attempted=attempted.copy())

        provider_name = "local"
        provider = self.providers[provider_name]
        attempted.append(provider_name)
        stats = self.reliability[provider_name]
        stats.attempts += 1
        started = time.perf_counter()
        yield ProviderStreamEvent("provider_start", provider_name, provider.model, reason="primary_providers_unavailable", attempted=attempted.copy())
        try:
            stream = provider.stream(
                provider_prompt,
                system_instruction=system_instruction,
                max_tokens=max_tokens,
            )
            first_chunk = await anext(stream)
            first_token_ms = round((time.perf_counter() - started) * 1000, 2)
            stats.successes += 1
            stats.total_first_token_ms += first_token_ms
            yield ProviderStreamEvent("first_token", provider_name, provider.model, text=first_chunk.text, latency_ms=first_token_ms, attempted=attempted.copy())
            if first_chunk.text:
                yield ProviderStreamEvent("token", provider_name, provider.model, text=first_chunk.text, latency_ms=first_token_ms, attempted=attempted.copy())
            async for chunk in stream:
                if chunk.text:
                    yield ProviderStreamEvent("token", provider_name, provider.model, text=chunk.text, attempted=attempted.copy())
            yield ProviderStreamEvent("completed", provider_name, provider.model, attempted=attempted.copy())
        except Exception as exc:
            stats.failures += 1
            stats.last_error = "local_response_error"
            emergency = self.providers["emergency"]
            attempted.append("emergency")
            yield ProviderStreamEvent("failover", provider_name, provider.model, reason="local_response_error", attempted=attempted.copy())
            async for chunk in emergency.stream(
                provider_prompt,
                system_instruction=system_instruction,
                max_tokens=max_tokens,
            ):
                if chunk.text:
                    yield ProviderStreamEvent("token", "emergency", emergency.model, text=chunk.text, attempted=attempted.copy())
            yield ProviderStreamEvent("completed", "emergency", emergency.model, attempted=attempted.copy())

    @staticmethod
    def _with_context(prompt: str, context: str) -> str:
        if not context.strip():
            return f"Current user message: {prompt}"
        return (
            "Recent conversation context, newest last:\n"
            f"{context.strip()}\n\n"
            f"Current user message: {prompt}"
        )

    async def status(self) -> Dict:
        availability = {}
        for name, provider in self.providers.items():
            stats = self.reliability[name]
            available = await provider.is_available()
            availability[name] = {
                "model": provider.model,
                "available": available,
                "reliability": {
                    "attempts": stats.attempts,
                    "successes": stats.successes,
                    "failures": stats.failures,
                    "last_error": stats.last_error,
                    "score": stats.score,
                    "avg_first_token_ms": stats.avg_first_token_ms,
                },
            }
        return availability


provider_manager = ProviderManager()
