from dataclasses import dataclass
from typing import AsyncIterator, Literal, Optional


ProviderName = Literal["openai", "perplexity", "ollama", "local", "emergency"]


@dataclass(frozen=True)
class ProviderChunk:
    text: str
    provider: ProviderName
    model: str
    is_final: bool = False


class ProviderError(Exception):
    def __init__(self, provider: ProviderName, reason: str, raw: Optional[str] = None) -> None:
        super().__init__(reason)
        self.provider = provider
        self.reason = reason
        self.raw = raw


class BaseProvider:
    name: ProviderName
    model: str

    async def is_available(self) -> bool:
        return True

    async def stream(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        raise NotImplementedError
