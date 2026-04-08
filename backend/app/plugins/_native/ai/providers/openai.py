"""OpenAI streaming provider — uses the Chat Completions API via httpx."""

import json
from collections.abc import AsyncGenerator

import httpx

from app.plugins._native.ai.providers.base import BaseAiProvider

_API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAiProvider(BaseAiProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", _API_URL, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                        content: str = (
                            obj.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError):
                        continue
