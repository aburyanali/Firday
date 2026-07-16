from typing import AsyncIterator

from openai import AsyncOpenAI

from config import config
from nova_backend.providers.unified_stream import BaseProvider, ProviderChunk, ProviderError


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self) -> None:
        self.model = config.openai_model
        self._client = AsyncOpenAI(api_key=config.openai_api_key) if config.openai_api_key else None

    async def is_available(self) -> bool:
        return self._client is not None

    async def stream(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        if self._client is None:
            raise ProviderError(self.name, "openai_not_configured")
        sys_prompt = system_instruction or "You are NOVA: calm, capable, direct, and warmly conversational. Address the user as sir naturally. Never mention internal systems or provider state."
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.55,
                max_tokens=max_tokens or 420,
                stream=True,
                timeout=config.provider_request_timeout_seconds,
            )
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield ProviderChunk(text=token, provider=self.name, model=self.model)
            yield ProviderChunk(text="", provider=self.name, model=self.model, is_final=True)
        except Exception as exc:
            raise ProviderError(self.name, classify_provider_error(str(exc)), str(exc)) from exc


def classify_provider_error(raw: str) -> str:
    text = raw.lower()
    if "429" in text or "rate" in text:
        return "rate_limited"
    if "quota" in text or "billing" in text:
        return "quota_exceeded"
    if "auth" in text or "api key" in text or "401" in text:
        return "auth_error"
    if "timeout" in text:
        return "timeout"
    return "provider_error"
