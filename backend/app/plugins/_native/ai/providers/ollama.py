"""Ollama streaming provider — uses the native `/api/chat` endpoint."""

import json
from collections.abc import AsyncGenerator

import httpx

from app.plugins._native.ai.providers.base import BaseAiProvider


class OllamaProvider(BaseAiProvider):
    """Talk to an Ollama server (default http://ollama:11434) via NDJSON streaming.

    Ollama exposes two chat surfaces: the native `/api/chat` (NDJSON, one JSON
    object per line with `message.content` deltas) and an OpenAI-compatible
    `/v1/chat/completions`. This adapter uses the native one so the payload is
    explicit and does not drift with upstream OpenAI-spec changes.
    """

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def stream(self, messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        # Ollama runs locally but large models can take a while to load into
        # memory and emit the first token; allow generous read timeouts.
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if not resp.is_success:
                    await resp.aread()
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # Ollama error payloads surface as `{"error": "..."}`.
                    if "error" in obj:
                        raise httpx.HTTPError(str(obj["error"]))
                    text: str = obj.get("message", {}).get("content", "")
                    if text:
                        yield text
                    if obj.get("done"):
                        break
