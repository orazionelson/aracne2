"""Orchestrator unit tests — fake provider, monkey-patched MCP dispatch.

The orchestrator is the most logic-dense module in the plugin; the
tests cover its branching independently of any LLM provider or MCP
backend so the suite stays fast and deterministic.

Coverage:

1. End-to-end happy path — text → end_turn → cleaned citations.
2. Two-round path — tool_use round → tool result → final round.
3. Citation enforcement — hallucinated (slug, filename) dropped.
4. Provider error — emits error event, returns OrchestratorResult.error.
5. Pure-function tests for extract_citations and enforce_citation_whitelist.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from app.plugins.mcp_server.auth import McpAuthContext
from app.plugins.nl_search import orchestrator
from app.plugins.nl_search.providers.base import (
    Done,
    ProviderError,
    TextChunk,
    ToolCallRequest,
    ToolDescriptor,
    ToolUseProvider,
    Usage,
)


# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeProvider(ToolUseProvider):
    """Yields a scripted sequence of events per round.

    ``rounds`` is a list of (events, stop_reason, usage) tuples; one
    is consumed per ``run_round`` call. Out of scripted rounds → the
    last one is repeated so an over-eager loop fails loudly via the
    test assertions rather than IndexError.
    """

    def __init__(
        self,
        rounds: list[tuple[list[Any], str, Usage]],
    ) -> None:
        self._rounds = rounds
        self._idx = 0

    async def run_round(  # type: ignore[override]
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[ToolDescriptor],
        timeout_s: float,
    ) -> AsyncGenerator[Any, None]:
        idx = min(self._idx, len(self._rounds) - 1)
        events, stop_reason, usage = self._rounds[idx]
        self._idx += 1
        for ev in events:
            yield ev
        yield Done(stop_reason=stop_reason, usage=usage)


class _FailingProvider(ToolUseProvider):
    async def run_round(  # type: ignore[override]
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[ToolDescriptor],
        timeout_s: float,
    ) -> AsyncGenerator[Any, None]:
        raise ProviderError("simulated network failure")
        yield  # pragma: no cover — required by AsyncGenerator typing


def _fake_ctx() -> McpAuthContext:
    """A bare ``McpAuthContext`` — fields are not inspected by the
    monkey-patched dispatch in these tests."""
    return McpAuthContext(token=None, corpus=None, collection_ids=frozenset())  # type: ignore[arg-type]


# ── Pure-function tests ───────────────────────────────────────────────────────


def test_extract_citations_finds_one_line_json_objects() -> None:
    answer = (
        "Here is the answer.\n\n"
        "## Citations\n"
        '{"slug": "manzoni", "filename": "letter_001.xml", "excerpt": "..."}\n'
        '{"slug": "manzoni", "filename": "letter_002.xml", "excerpt": "..."}\n'
    )
    out = orchestrator.extract_citations(answer)
    assert len(out) == 2
    assert out[0]["slug"] == "manzoni"
    assert out[0]["filename"] == "letter_001.xml"


def test_extract_citations_only_after_last_heading() -> None:
    answer = (
        "## Citations earlier\n"
        '{"slug": "x", "filename": "a.xml"}\n'
        "Some more body text.\n"
        "## Citations\n"
        '{"slug": "y", "filename": "b.xml"}\n'
    )
    out = orchestrator.extract_citations(answer)
    assert [c["filename"] for c in out] == ["b.xml"]


def test_enforce_citation_whitelist_drops_unknown_pairs() -> None:
    citations = [
        {"slug": "real", "filename": "a.xml", "excerpt": ""},
        {"slug": "fake", "filename": "z.xml", "excerpt": ""},
    ]
    whitelist = {("real", "a.xml")}
    out = orchestrator.enforce_citation_whitelist(citations, whitelist)
    assert [c["filename"] for c in out] == ["a.xml"]


# ── Orchestrator loop ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_single_round_end_turn(monkeypatch) -> None:
    """A provider that goes straight to end_turn with text → no tool dispatch."""

    async def fake_dispatch(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("dispatch should not be called")

    monkeypatch.setattr(
        "app.plugins.nl_search.orchestrator.mcp_dispatch", fake_dispatch
    )

    provider = _FakeProvider(
        rounds=[
            (
                [TextChunk(text="Final answer.\n## Citations\n")],
                "end_turn",
                Usage(input_tokens=10, output_tokens=2),
            ),
        ]
    )

    events: list[Any] = []
    async for ev in orchestrator.run(
        db=None,  # type: ignore[arg-type]
        provider=provider,
        provider_kind="ollama",
        ctx=_fake_ctx(),
        query="Hello?",
        system_prompt="be honest",
        timeout_s=5.0,
        max_rounds=4,
    ):
        events.append(ev)

    names = [
        e.name
        for e in events
        if isinstance(e, orchestrator.OrchestratorEvent)
    ]
    assert "chunk" in names
    assert names[-2:] == ["citations", "done"]
    result = next(
        e for e in events if isinstance(e, orchestrator.OrchestratorResult)
    )
    assert result.rounds == 1
    assert result.total_usage.input_tokens == 10
    assert result.error is None


@pytest.mark.asyncio
async def test_run_two_round_tool_use(monkeypatch) -> None:
    """Round 1: tool call → MCP dispatch → result. Round 2: end_turn."""

    dispatch_calls: list[str] = []

    async def fake_dispatch(payload, *, db, ctx):  # noqa: ANN001
        dispatch_calls.append(payload["params"]["name"])
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '[{"slug": "manzoni", "filename": "letter_001.xml"}]'
                        ),
                    }
                ],
                "isError": False,
            }
        }

    monkeypatch.setattr(
        "app.plugins.nl_search.orchestrator.mcp_dispatch", fake_dispatch
    )

    provider = _FakeProvider(
        rounds=[
            (
                [
                    TextChunk(text="Let me search.\n"),
                    ToolCallRequest(
                        id="t1",
                        name="search_entities",
                        arguments={"query": "Manzoni"},
                    ),
                ],
                "tool_use",
                Usage(input_tokens=20, output_tokens=10),
            ),
            (
                [
                    TextChunk(
                        text=(
                            "Found one document.\n"
                            "## Citations\n"
                            '{"slug": "manzoni", "filename": "letter_001.xml", "excerpt": "..."}\n'
                        )
                    ),
                ],
                "end_turn",
                Usage(input_tokens=80, output_tokens=15),
            ),
        ]
    )

    events: list[Any] = []
    async for ev in orchestrator.run(
        db=None,  # type: ignore[arg-type]
        provider=provider,
        provider_kind="ollama",
        ctx=_fake_ctx(),
        query="Tell me about Manzoni",
        system_prompt="be honest",
        timeout_s=5.0,
        max_rounds=4,
    ):
        events.append(ev)

    assert dispatch_calls == ["search_entities"]
    citations = next(
        e for e in events
        if isinstance(e, orchestrator.OrchestratorEvent) and e.name == "citations"
    )
    assert citations.data["items"][0]["filename"] == "letter_001.xml"
    result = next(
        e for e in events if isinstance(e, orchestrator.OrchestratorResult)
    )
    assert result.rounds == 2
    assert result.total_usage.input_tokens == 100  # 20 + 80


@pytest.mark.asyncio
async def test_run_drops_hallucinated_citation(monkeypatch) -> None:
    """Tool returned `manzoni`; model also cites `fake_doc` → dropped."""

    async def fake_dispatch(payload, *, db, ctx):  # noqa: ANN001
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '[{"slug": "manzoni", "filename": "real.xml"}]',
                    }
                ],
                "isError": False,
            }
        }

    monkeypatch.setattr(
        "app.plugins.nl_search.orchestrator.mcp_dispatch", fake_dispatch
    )

    provider = _FakeProvider(
        rounds=[
            (
                [
                    ToolCallRequest(
                        id="t1",
                        name="search_entities",
                        arguments={"query": "x"},
                    ),
                ],
                "tool_use",
                Usage(input_tokens=10, output_tokens=5),
            ),
            (
                [
                    TextChunk(
                        text=(
                            "Here is the answer.\n"
                            "## Citations\n"
                            '{"slug": "manzoni", "filename": "real.xml", "excerpt": ""}\n'
                            '{"slug": "fake_doc", "filename": "z.xml", "excerpt": ""}\n'
                        )
                    ),
                ],
                "end_turn",
                Usage(input_tokens=20, output_tokens=8),
            ),
        ]
    )

    events: list[Any] = []
    async for ev in orchestrator.run(
        db=None,  # type: ignore[arg-type]
        provider=provider,
        provider_kind="ollama",
        ctx=_fake_ctx(),
        query="…",
        system_prompt="…",
        timeout_s=5.0,
        max_rounds=4,
    ):
        events.append(ev)

    citations = next(
        e for e in events
        if isinstance(e, orchestrator.OrchestratorEvent) and e.name == "citations"
    )
    filenames = [c["filename"] for c in citations.data["items"]]
    assert filenames == ["real.xml"]
    assert "z.xml" not in filenames


@pytest.mark.asyncio
async def test_run_provider_error_emits_error_event(monkeypatch) -> None:
    """ProviderError → ``error`` event + Result.error set."""

    async def fake_dispatch(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("not reached")

    monkeypatch.setattr(
        "app.plugins.nl_search.orchestrator.mcp_dispatch", fake_dispatch
    )

    provider = _FailingProvider()

    events: list[Any] = []
    async for ev in orchestrator.run(
        db=None,  # type: ignore[arg-type]
        provider=provider,
        provider_kind="ollama",
        ctx=_fake_ctx(),
        query="…",
        system_prompt="…",
        timeout_s=5.0,
        max_rounds=4,
    ):
        events.append(ev)

    error_evs = [
        e
        for e in events
        if isinstance(e, orchestrator.OrchestratorEvent) and e.name == "error"
    ]
    assert error_evs
    assert error_evs[0].data["code"] == "PROVIDER_ERROR"
    result = next(
        e for e in events if isinstance(e, orchestrator.OrchestratorResult)
    )
    assert result.error is not None
