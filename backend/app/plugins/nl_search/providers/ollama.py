"""Ollama tool-use adapter — POST /api/chat with the ``tools`` parameter.

Local provider, default for the natural-language search plugin's
safe-posture configuration. Reports zero token counts so the budget
layer treats every call as $0.

Wire format reference: https://github.com/ollama/ollama/blob/main/docs/api.md
The OpenAI-compatible function-calling shape is used (``tool_calls``
under ``message`` on responses; ``tools`` array on requests).
"""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog

from app.plugins.nl_search.providers.base import (
    Done,
    ProviderError,
    TextChunk,
    ToolCallRequest,
    ToolDescriptor,
    ToolUseProvider,
    Usage,
)

logger = structlog.get_logger()


def _new_call_id() -> str:
    """Synthesize a tool-call correlation id.

    Ollama does not return ``id`` on tool_calls; the orchestrator
    needs one to pair the request with the eventual ``tool_result``,
    so we mint a short random token and echo it as the ``role: tool``
    message's ``name`` on the next round.
    """
    return f"call_{secrets.token_hex(6)}"


class OllamaToolUseProvider(ToolUseProvider):
    """Adapter against an Ollama server's ``/api/chat`` endpoint."""

    def __init__(self, *, host: str, model: str) -> None:
        self._host = host.rstrip("/")
        self._model = model

    async def run_round(  # type: ignore[override]
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[ToolDescriptor],
        timeout_s: float,
    ) -> AsyncGenerator[TextChunk | ToolCallRequest | Done, None]:
        payload = {
            "model": self._model,
            "messages": messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ],
            "stream": False,
            "options": {"num_ctx": 8192},
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    f"{self._host}/api/chat", json=payload
                )
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                body = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Ollama returned malformed JSON: {exc}") from exc

        message = body.get("message") or {}
        text = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []

        if text:
            yield TextChunk(text=text)

        had_tool_calls = False
        for raw in tool_calls:
            fn = raw.get("function") or {}
            name = fn.get("name")
            args = fn.get("arguments")
            if not isinstance(name, str):
                continue
            # Ollama can return arguments as either a dict or a JSON string.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            if not isinstance(args, dict):
                args = {}
            had_tool_calls = True
            yield ToolCallRequest(id=_new_call_id(), name=name, arguments=args)

        # Ollama's done_reason can be ``"stop"``, ``"length"``, … — we
        # only care whether tool_calls were emitted, which is what
        # decides whether the orchestrator loops.
        stop_reason = "tool_use" if had_tool_calls else "end_turn"
        usage = Usage(
            input_tokens=int(body.get("prompt_eval_count") or 0),
            output_tokens=int(body.get("eval_count") or 0),
        )
        yield Done(stop_reason=stop_reason, usage=usage)
