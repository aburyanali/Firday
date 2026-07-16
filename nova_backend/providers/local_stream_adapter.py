import asyncio
from typing import AsyncIterator

from nova_backend.providers.unified_stream import ProviderChunk, ProviderName


async def paced_stream(
    text: str,
    provider: ProviderName,
    model: str,
    delay_seconds: float = 0.006,
) -> AsyncIterator[ProviderChunk]:
    words = text.split(" ")
    for index, word in enumerate(words):
        yield ProviderChunk(
            text=word + (" " if index < len(words) - 1 else ""),
            provider=provider,
            model=model,
        )
        await asyncio.sleep(delay_seconds)
    yield ProviderChunk(text="", provider=provider, model=model, is_final=True)
