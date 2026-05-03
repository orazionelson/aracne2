"""Provider adapter tests — wire-format round trips with mocked HTTP.

Both adapters convert one HTTP round-trip into a flat sequence of
:class:`TextChunk` / :class:`ToolCallRequest` / :class:`Done` events.
The tests assert the event shape for the four cases we care about:

1. Plain text answer (no tool calls) → text + Done(end_turn).
2. Tool-use round → ToolCallRequest events + Done(tool_use).
3. Mixed (text + tool calls) → both kinds of events in order.
4. HTTP error → :class:`ProviderError`.

For Ollama we additionally check that string-encoded ``arguments``
are JSON-decoded — the upstream wire format is inconsistent on this
point and we want one canonical dict shape downstream.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.plugins.nl_search.providers.anthropic import AnthropicToolUseProvider
from app.plugins.nl_search.providers.base import (
    Done,
    ProviderError,
    TextChunk,
    ToolCallRequest,
    ToolDescriptor,
)
from app.plugins.nl_search.providers.ollama import OllamaToolUseProvider


# ── Helpers ───────────────────────────────────────────────────────────────────


def _tools() -> list[ToolDescriptor]:
    return [
        ToolDescriptor(
            name="search_entities",
            description="Search the named-entities index.",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        ),
    ]


async def _drain(provider, *, messages):
    events = []
    async for ev in provider.run_round(
        messages=messages, tools=_tools(), timeout_s=5.0
    ):
        events.append(ev)
    return events


def _patch_httpx_post(monkeypatch, response_factory):
    """Intercept every ``httpx.AsyncClient.post`` call inside this test."""
    real_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):  # noqa: ANN001 — test scaffold
        kwargs["transport"] = httpx.MockTransport(response_factory)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


# ── Ollama ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ollama_plain_text_response(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Hello world."},
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 4,
            },
        )

    _patch_httpx_post(monkeypatch, handler)
    provider = OllamaToolUseProvider(host="http://x", model="llama3.1")

    events = await _drain(provider, messages=[{"role": "user", "content": "hi"}])

    assert any(isinstance(e, TextChunk) and e.text == "Hello world." for e in events)
    done = [e for e in events if isinstance(e, Done)]
    assert len(done) == 1
    assert done[0].stop_reason == "end_turn"
    assert done[0].usage.input_tokens == 10
    assert done[0].usage.output_tokens == 4


@pytest.mark.asyncio
async def test_ollama_tool_call_request(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_entities",
                                "arguments": {"query": "Manzoni"},
                            }
                        }
                    ],
                },
                "done_reason": "stop",
            },
        )

    _patch_httpx_post(monkeypatch, handler)
    provider = OllamaToolUseProvider(host="http://x", model="llama3.1")

    events = await _drain(provider, messages=[{"role": "user", "content": "hi"}])

    calls = [e for e in events if isinstance(e, ToolCallRequest)]
    assert len(calls) == 1
    assert calls[0].name == "search_entities"
    assert calls[0].arguments == {"query": "Manzoni"}
    assert calls[0].id.startswith("call_")
    done = [e for e in events if isinstance(e, Done)]
    assert done[0].stop_reason == "tool_use"


@pytest.mark.asyncio
async def test_ollama_arguments_as_json_string(monkeypatch) -> None:
    """Ollama can serialise ``arguments`` as a JSON string — decode it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_entities",
                                "arguments": json.dumps({"query": "Manzoni"}),
                            }
                        }
                    ],
                },
                "done_reason": "stop",
            },
        )

    _patch_httpx_post(monkeypatch, handler)
    provider = OllamaToolUseProvider(host="http://x", model="llama3.1")

    events = await _drain(provider, messages=[{"role": "user", "content": "hi"}])
    calls = [e for e in events if isinstance(e, ToolCallRequest)]
    assert calls[0].arguments == {"query": "Manzoni"}


@pytest.mark.asyncio
async def test_ollama_http_error_raises_provider_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    _patch_httpx_post(monkeypatch, handler)
    provider = OllamaToolUseProvider(host="http://x", model="llama3.1")

    with pytest.raises(ProviderError):
        await _drain(provider, messages=[{"role": "user", "content": "hi"}])


# ── Anthropic ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_text_and_tool_use_blocks(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "Let me search the corpus."},
                    {
                        "type": "tool_use",
                        "id": "toolu_abc123",
                        "name": "search_entities",
                        "input": {"query": "Manzoni"},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 32, "output_tokens": 17},
            },
        )

    _patch_httpx_post(monkeypatch, handler)
    provider = AnthropicToolUseProvider(
        api_key="sk-test", model="claude-sonnet-4-6", system_prompt="…"
    )

    events = await _drain(
        provider,
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )

    text = [e for e in events if isinstance(e, TextChunk)]
    assert text and text[0].text == "Let me search the corpus."
    calls = [e for e in events if isinstance(e, ToolCallRequest)]
    assert len(calls) == 1
    assert calls[0].id == "toolu_abc123"
    assert calls[0].name == "search_entities"
    assert calls[0].arguments == {"query": "Manzoni"}
    done = [e for e in events if isinstance(e, Done)]
    assert done[0].stop_reason == "tool_use"
    assert done[0].usage.input_tokens == 32
    assert done[0].usage.output_tokens == 17


@pytest.mark.asyncio
async def test_anthropic_end_turn_pure_text(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Final answer."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 5},
            },
        )

    _patch_httpx_post(monkeypatch, handler)
    provider = AnthropicToolUseProvider(
        api_key="sk-test", model="claude-sonnet-4-6", system_prompt="…"
    )

    events = await _drain(
        provider,
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )

    text = [e for e in events if isinstance(e, TextChunk)]
    assert text and text[0].text == "Final answer."
    done = [e for e in events if isinstance(e, Done)]
    assert done[0].stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_anthropic_http_error_raises_provider_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    _patch_httpx_post(monkeypatch, handler)
    provider = AnthropicToolUseProvider(
        api_key="sk-test", model="claude-sonnet-4-6", system_prompt="…"
    )

    with pytest.raises(ProviderError):
        await _drain(
            provider,
            messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        )
