"""Anthropic tool-use adapter — Messages API with the ``tools`` parameter.

Cloud provider, billed. Opt-in via ``nl_search_provider=anthropic`` +
``nl_search_api_key`` (Fernet-encrypted at rest in ``system_settings``).

We deliberately do NOT stream the LLM response — tool-use rounds are
fetched in one shot, then the orchestrator emits its own SSE events
to the browser based on what each round contains. Streaming the
provider's own SSE while interleaving tool calls is complex; it can
be added later if perceived latency becomes a concern.

Wire format reference:
https://docs.anthropic.com/en/api/messages
https://docs.anthropic.com/en/docs/build-with-claude/tool-use
"""

from __future__ import annotations

import json
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

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_MAX_TOKENS = 2048


class AnthropicToolUseProvider(ToolUseProvider):
    """Adapter against Anthropic's Messages API.

    The orchestrator builds the ``messages`` list in Anthropic's
    structured-content shape directly — content blocks with
    ``type: text`` / ``type: tool_use`` / ``type: tool_result``.
    """

    def __init__(self, *, api_key: str, model: str, system_prompt: str) -> None:
        self._api_key = api_key
        self._model = model
        self._system_prompt = system_prompt

    async def run_round(  # type: ignore[override]
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[ToolDescriptor],
        timeout_s: float,
    ) -> AsyncGenerator[TextChunk | ToolCallRequest | Done, None]:
        payload = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "system": self._system_prompt,
            "messages": messages,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(_API_URL, headers=headers, json=payload)
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"Anthropic returned HTTP {resp.status_code}: "
                        f"{resp.text[:200]}"
                    )
                body = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Anthropic returned malformed JSON: {exc}"
            ) from exc

        content_blocks = body.get("content") or []
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text = block.get("text") or ""
                if text:
                    yield TextChunk(text=text)
            elif btype == "tool_use":
                tid = block.get("id")
                name = block.get("name")
                args = block.get("input") or {}
                if not isinstance(tid, str) or not isinstance(name, str):
                    continue
                if not isinstance(args, dict):
                    args = {}
                yield ToolCallRequest(id=tid, name=name, arguments=args)

        stop_reason = body.get("stop_reason") or "end_turn"
        usage_raw = body.get("usage") or {}
        usage = Usage(
            input_tokens=int(usage_raw.get("input_tokens") or 0),
            output_tokens=int(usage_raw.get("output_tokens") or 0),
        )
        yield Done(stop_reason=stop_reason, usage=usage)
