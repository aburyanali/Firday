from typing import AsyncIterator

from openai import AsyncOpenAI

from config import config
from nova_backend.providers.openai_provider import classify_provider_error
from nova_backend.providers.unified_stream import BaseProvider, ProviderChunk, ProviderError


class PerplexityProvider(BaseProvider):
    name = "perplexity"

    def __init__(self) -> None:
        self.model = config.perplexity_model
        self._client = (
            AsyncOpenAI(api_key=config.perplexity_api_key, base_url="https://api.perplexity.ai")
            if config.perplexity_api_key
            else None
        )

    async def is_available(self) -> bool:
        return self._client is not None

    async def stream(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        if self._client is None:
            raise ProviderError(self.name, "perplexity_not_configured")
        sys_prompt = system_instruction or "Answer with current factual clarity. Keep it concise and do not expose citations unless asked."
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": sys_prompt,
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.35,
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
