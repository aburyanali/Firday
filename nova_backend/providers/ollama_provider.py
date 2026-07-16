import json
from typing import AsyncIterator, Iterable

import httpx

from config import config
from nova_backend.providers.unified_stream import BaseProvider, ProviderChunk, ProviderError


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or config.ollama_model
        self.base_url = (base_url or config.ollama_base_url).rstrip("/")
        self._detected_model: str | None = None

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=0.6) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False
                self._detected_model = self._select_model(response.json().get("models", []))
                if self._detected_model:
                    self.model = self._detected_model
                return bool(self.model)
        except Exception:
            return False

    async def stream(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        if not self._detected_model:
            await self.is_available()
        sys_prompt = system_instruction or (
            "You are NOVA, a calm desktop assistant presence. Speak naturally and directly. "
            "You are calm, intelligent, emotionally aware, practical, and concise. "
            "Address the user as sir naturally in conversational replies. "
            "Never mention internal systems, routing, providers, fallback, or degraded mode. "
            "Use recent context quietly without announcing it."
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": sys_prompt,
                },
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "options": {
                "temperature": 0.62,
                "top_p": 0.88,
                "num_predict": max_tokens or 420,
                "num_ctx": 4096,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status_code >= 400:
                        raise ProviderError(self.name, "ollama_http_error", str(response.status_code))
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield ProviderChunk(text=token, provider=self.name, model=self.model)
                        if data.get("done"):
                            yield ProviderChunk(text="", provider=self.name, model=self.model, is_final=True)
                            return
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(self.name, "ollama_unavailable", str(exc)) from exc

    def _select_model(self, models: Iterable[dict]) -> str | None:
        names = [str(model.get("name", "")) for model in models if model.get("name")]
        if self.model:
            for name in names:
                if name == self.model or name.startswith(f"{self.model}:"):
                    return name

        preferred = ("llama3", "qwen2.5", "mistral")
        for prefix in preferred:
            for name in names:
                if name.startswith(prefix):
                    return name
        return names[0] if names else None
