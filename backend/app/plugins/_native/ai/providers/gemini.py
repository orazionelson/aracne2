"""Google Gemini streaming provider — uses the generateContent REST API via httpx."""

import json
from collections.abc import AsyncGenerator

import httpx

from app.plugins._native.ai.providers.base import BaseAiProvider

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseAiProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        url = f"{_BASE_URL}/{self._model}:streamGenerateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                url,
                params={"key": self._api_key, "alt": "sse"},
                json=payload,
            ) as resp:
                if not resp.is_success:
                    await resp.aread()  # buffer error body so .text is readable after raise
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    try:
                        obj = json.loads(data)
                        parts = (
                            obj.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [])
                        )
                        for part in parts:
                            text: str = part.get("text", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, IndexError):
                        continue
