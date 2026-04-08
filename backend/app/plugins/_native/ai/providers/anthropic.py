"""Anthropic streaming provider — uses the Messages API via httpx."""

import json
from collections.abc import AsyncGenerator

import httpx

from app.plugins._native.ai.providers.base import BaseAiProvider

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_MAX_TOKENS = 2048


class AnthropicProvider(BaseAiProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", _API_URL, headers=headers, json=payload) as resp:
                if not resp.is_success:
                    await resp.aread()  # buffer error body so .text is readable after raise
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    try:
                        obj = json.loads(data)
                        if obj.get("type") == "content_block_delta":
                            text: str = obj.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        continue
