"""Tool-use loop — drives the LLM, dispatches MCP tools, enforces citations.

Phase NLS-C. The orchestrator is provider-agnostic: it consumes the
flat event stream emitted by :class:`ToolUseProvider` and emits its
own SSE-shaped events back to the endpoint. The endpoint serialises
those to ``text/event-stream`` and (optionally) caches them.

Flow per request:

1. Build the system prompt + first user message.
2. Loop up to ``nl_search_max_tool_rounds`` rounds:
   - Call ``provider.run_round`` and collect every ``TextChunk`` /
     ``ToolCallRequest`` it yields.
   - Forward text as ``answer_chunk`` events to the endpoint.
   - For each tool call: emit a ``tool_call_start`` status event,
     dispatch through ``app.plugins.mcp_server.server.dispatch()``,
     emit ``tool_call_done``, append the request + result to the
     conversation in the provider's wire format.
   - Stop on ``stop_reason == end_turn`` or on tool-round budget hit.
3. Post-validate the assistant's citations: every ``{slug, filename}``
   pair claimed in the answer must appear in the tool-call history.
4. Emit ``citations`` + ``done``.

The orchestrator also tracks token usage per round, hands it back so
the endpoint can call :func:`budget.record_spend`, and adopts a
provider-agnostic ``citations_extracted`` strategy that scans the
``## Citations`` block at the bottom of the answer for one-line JSON
objects (the system prompt instructs the LLM to format them this way).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.corpus import Corpus
from app.plugins.mcp_server.auth import McpAuthContext
from app.plugins.mcp_server.server import TOOLS as MCP_TOOLS
from app.plugins.mcp_server.server import dispatch as mcp_dispatch
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


# Confirmed read subset (decision 4 in the §25 brainstorm).
_NL_SEARCH_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_entities",
        "find_entity_occurrences",
        "get_collection",
        "list_documents",
        "get_document_source",
        "tei_to_text",
    }
)


@dataclass
class OrchestratorEvent:
    """SSE-shaped event the endpoint forwards to the browser.

    ``name`` is the SSE ``event:`` field; ``data`` becomes the
    ``data:`` JSON payload. Cached payloads serialise this dataclass
    via ``asdict``.
    """

    name: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    """Aggregate emitted at the end of :func:`run`.

    Used by the endpoint to update the budget table and to derive a
    cache key. Distinct from :class:`OrchestratorEvent` so that the
    transport layer does not need to inspect events to compute spend.
    """

    total_usage: Usage
    rounds: int
    error: str | None = None


def build_tool_manifest() -> list[ToolDescriptor]:
    """Return the descriptors for the confirmed NL-search read subset.

    Reuses the JSON schemas already declared in
    ``app.plugins.mcp_server.server.TOOLS`` so the wire format the LLM
    sees is identical to the editor's MCP path.
    """
    out: list[ToolDescriptor] = []
    for spec in MCP_TOOLS:
        if spec.name not in _NL_SEARCH_TOOL_NAMES:
            continue
        out.append(
            ToolDescriptor(
                name=spec.name,
                description=spec.description,
                input_schema=spec.schema,
            )
        )
    return out


async def build_synthetic_ctx(
    db: AsyncSession, *, corpus_id: str
) -> McpAuthContext | None:
    """Resolve the configured corpus into a synthetic MCP auth context.

    Returns ``None`` when ``corpus_id`` is empty or the row is gone —
    the caller surfaces that as a 503 ``CORPUS_NOT_CONFIGURED`` so
    the operator can pick a corpus from /admin/corpora before the
    endpoint serves traffic.

    The returned context has ``token=None``-shaped fields zeroed out
    in spirit — the dispatch layer never inspects ``ctx.token`` for
    the NL-search read subset, so no real ``McpToken`` is needed.
    """
    if not corpus_id:
        return None
    try:
        cid = uuid.UUID(corpus_id)
    except ValueError:
        return None
    corpus = await db.scalar(select(Corpus).where(Corpus.id == cid))
    if corpus is None:
        return None
    collection_ids = frozenset(c.id for c in corpus.collections)
    # We mint a placeholder McpToken-shaped object purely so the
    # dataclass typecheck is happy. ``token`` is never read by any
    # tool in the read subset (verified by inspection).
    from app.models.corpus import McpToken
    placeholder_token = McpToken(
        id=uuid.UUID(int=0),
        corpus_id=corpus.id,
        label="nl_search:synthetic",
        hashed_token="",
    )
    return McpAuthContext(
        token=placeholder_token,
        corpus=corpus,
        collection_ids=collection_ids,
    )


# ── Citation enforcement ──────────────────────────────────────────────────────


_CITATION_LINE_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def extract_citations(answer_text: str) -> list[dict[str, str]]:
    """Pull ``{slug, filename, excerpt}`` JSON objects from the answer.

    The system prompt instructs the LLM to end with a
    ``## Citations`` (or ``## Citazioni``) heading followed by one
    JSON object per line. We scan from the *last* such heading to
    end-of-text so a model who mentions citations earlier doesn't
    pollute the list.
    """
    lower = answer_text.lower()
    cut = max(
        lower.rfind("## citations"),
        lower.rfind("## citazioni"),
        lower.rfind("citations:"),
        lower.rfind("citazioni:"),
    )
    tail = answer_text[cut:] if cut >= 0 else answer_text
    out: list[dict[str, str]] = []
    for match in _CITATION_LINE_RE.finditer(tail):
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        slug = obj.get("slug")
        filename = obj.get("filename")
        if not isinstance(slug, str) or not isinstance(filename, str):
            continue
        excerpt = obj.get("excerpt")
        out.append(
            {
                "slug": slug,
                "filename": filename,
                "excerpt": excerpt if isinstance(excerpt, str) else "",
            }
        )
    return out


def enforce_citation_whitelist(
    citations: list[dict[str, str]],
    whitelist: set[tuple[str, str]],
) -> list[dict[str, str]]:
    """Drop citations whose ``(slug, filename)`` is not in the whitelist.

    The whitelist is built from every ``{slug, filename}`` pair the
    orchestrator saw in tool results during the conversation. A
    citation outside the whitelist is, by definition, hallucinated.
    """
    return [c for c in citations if (c["slug"], c["filename"]) in whitelist]


# ── Tool result harvesting ────────────────────────────────────────────────────


def _harvest_pairs(payload: Any, into: set[tuple[str, str]]) -> None:
    """Walk a tool-result payload and extract every ``(slug, filename)``.

    Tool results are JSON-encodable Python objects of various shapes
    (lists of dicts, single dicts, mixed). We do a recursive scan so
    a future tool that nests document refs differently still
    contributes its pairs.
    """
    if isinstance(payload, dict):
        slug = payload.get("slug") or payload.get("collection_slug")
        filename = payload.get("filename")
        if isinstance(slug, str) and isinstance(filename, str):
            into.add((slug, filename))
        for v in payload.values():
            _harvest_pairs(v, into)
    elif isinstance(payload, list):
        for item in payload:
            _harvest_pairs(item, into)


# ── The loop itself ───────────────────────────────────────────────────────────


def _build_initial_messages(
    *, query: str, system_prompt: str, provider_kind: str
) -> list[dict[str, Any]]:
    """Assemble the first ``messages`` list in the wire format the
    selected provider expects.

    Anthropic carries the system prompt out-of-band (its provider
    constructor took it). Ollama carries it as the first
    ``role: system`` message inside the array.
    """
    if provider_kind == "anthropic":
        return [
            {
                "role": "user",
                "content": [{"type": "text", "text": query}],
            }
        ]
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]


def _append_assistant_round(
    messages: list[dict[str, Any]],
    *,
    text: str,
    tool_calls: list[ToolCallRequest],
    provider_kind: str,
) -> None:
    if provider_kind == "anthropic":
        blocks: list[dict[str, Any]] = []
        if text:
            blocks.append({"type": "text", "text": text})
        for tc in tool_calls:
            blocks.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                }
            )
        messages.append({"role": "assistant", "content": blocks})
    else:
        msg: dict[str, Any] = {"role": "assistant"}
        if text:
            msg["content"] = text
        else:
            msg["content"] = ""
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                }
                for tc in tool_calls
            ]
        messages.append(msg)


def _append_tool_result(
    messages: list[dict[str, Any]],
    *,
    tool_call: ToolCallRequest,
    result_payload: Any,
    is_error: bool,
    provider_kind: str,
) -> None:
    serialised = json.dumps(result_payload, ensure_ascii=False, default=str)
    if provider_kind == "anthropic":
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": serialised,
                        "is_error": is_error,
                    }
                ],
            }
        )
    else:
        messages.append(
            {
                "role": "tool",
                "name": tool_call.name,
                "content": serialised,
            }
        )


async def _dispatch_one_tool(
    db: AsyncSession,
    *,
    ctx: McpAuthContext,
    tool_call: ToolCallRequest,
) -> tuple[Any, bool]:
    """Run one tool through the MCP dispatcher.

    Returns ``(payload, is_error)`` — payload is the JSON body the
    LLM gets back, is_error mirrors the MCP ``isError`` flag so a
    failed tool call is communicated to the model rather than
    swallowed.
    """
    request = {
        "jsonrpc": "2.0",
        "id": tool_call.id,
        "method": "tools/call",
        "params": {"name": tool_call.name, "arguments": tool_call.arguments},
    }
    response = await mcp_dispatch(request, db=db, ctx=ctx)
    result = response.get("result") or {}
    raw_content = result.get("content") or []
    payload: Any = None
    if isinstance(raw_content, list) and raw_content:
        first = raw_content[0]
        if isinstance(first, dict):
            text = first.get("text")
            if isinstance(text, str):
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = text
    is_error = bool(result.get("isError"))
    return payload, is_error


async def run(
    db: AsyncSession,
    *,
    provider: ToolUseProvider,
    provider_kind: str,
    ctx: McpAuthContext,
    query: str,
    system_prompt: str,
    timeout_s: float,
    max_rounds: int,
) -> AsyncGenerator[OrchestratorEvent | OrchestratorResult, None]:
    """Run the LLM tool-use loop.

    Yields :class:`OrchestratorEvent` instances as they need to be
    emitted on the SSE stream, and exactly one :class:`OrchestratorResult`
    at the very end with the aggregate usage / round count / error.
    """
    tools = build_tool_manifest()
    messages = _build_initial_messages(
        query=query, system_prompt=system_prompt, provider_kind=provider_kind
    )
    answer_so_far: list[str] = []
    citation_whitelist: set[tuple[str, str]] = set()
    total = Usage(input_tokens=0, output_tokens=0)
    rounds_done = 0

    yield OrchestratorEvent(name="status", data={"phase": "thinking"})

    for _ in range(max(1, max_rounds)):
        rounds_done += 1
        round_text: list[str] = []
        round_tool_calls: list[ToolCallRequest] = []
        try:
            async for ev in provider.run_round(
                messages=messages, tools=tools, timeout_s=timeout_s
            ):
                if isinstance(ev, TextChunk):
                    round_text.append(ev.text)
                    answer_so_far.append(ev.text)
                    yield OrchestratorEvent(
                        name="chunk", data={"text": ev.text}
                    )
                elif isinstance(ev, ToolCallRequest):
                    round_tool_calls.append(ev)
                elif isinstance(ev, Done):
                    total = Usage(
                        input_tokens=total.input_tokens + ev.usage.input_tokens,
                        output_tokens=total.output_tokens + ev.usage.output_tokens,
                    )
                    stop_reason = ev.stop_reason
                    break
            else:
                stop_reason = "end_turn"  # generator exhausted without Done
        except ProviderError as exc:
            logger.error("nl_search_provider_error", error=str(exc))
            yield OrchestratorEvent(
                name="error",
                data={"code": "PROVIDER_ERROR", "message": str(exc)},
            )
            yield OrchestratorResult(
                total_usage=total, rounds=rounds_done, error=str(exc)
            )
            return

        _append_assistant_round(
            messages,
            text="".join(round_text),
            tool_calls=round_tool_calls,
            provider_kind=provider_kind,
        )

        if not round_tool_calls:
            # No tool calls and provider says end_turn → final answer.
            break

        for tc in round_tool_calls:
            yield OrchestratorEvent(
                name="status",
                data={"phase": "tool_call", "name": tc.name},
            )
            try:
                payload, is_error = await _dispatch_one_tool(
                    db, ctx=ctx, tool_call=tc
                )
            except Exception as exc:  # noqa: BLE001 — surface to model
                logger.error(
                    "nl_search_tool_dispatch_error",
                    tool=tc.name,
                    error=str(exc),
                )
                payload = {"error": str(exc)}
                is_error = True
            if not is_error:
                _harvest_pairs(payload, citation_whitelist)
            yield OrchestratorEvent(
                name="status",
                data={"phase": "tool_done", "name": tc.name, "is_error": is_error},
            )
            _append_tool_result(
                messages,
                tool_call=tc,
                result_payload=payload,
                is_error=is_error,
                provider_kind=provider_kind,
            )

        if stop_reason == "end_turn":
            # Model emitted end_turn alongside tool calls — rare but
            # provider-dependent. Trust the signal and stop looping.
            break

    final_answer = "".join(answer_so_far)
    raw_citations = extract_citations(final_answer)
    cleaned = enforce_citation_whitelist(raw_citations, citation_whitelist)
    yield OrchestratorEvent(name="citations", data={"items": cleaned})
    yield OrchestratorEvent(name="done", data={})
    yield OrchestratorResult(total_usage=total, rounds=rounds_done)


__all__ = [
    "OrchestratorEvent",
    "OrchestratorResult",
    "build_tool_manifest",
    "build_synthetic_ctx",
    "extract_citations",
    "enforce_citation_whitelist",
    "run",
]
