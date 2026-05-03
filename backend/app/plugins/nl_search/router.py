"""HTTP entrypoint — POST /api/v1/nl-search/query  (SSE).

Phase NLS-D. Sequence per request:

1. **Rate limit** — slowapi, per IP. Anonymous mode: 3/min, 30/day.
2. **Auth gate** — when ``nl_search_require_login`` is on (default),
   a missing ``request.state.user`` triggers 401.
3. **Budget gate** — today's spend ≥ ``nl_search_daily_budget_eur``
   short-circuits to 503 ``BUDGET_EXCEEDED``.
4. **Concurrency gate** — :func:`acquire_concurrency_slot` raises
   :class:`OverCapacityError` (503) when the configured slots are
   exhausted.
5. **Cache lookup** — on hit, replay the cached SSE-event list and
   return immediately. No tool dispatch, no LLM round-trip.
6. **Orchestrator run** — emit events as they arrive; estimate and
   record spend after the run; store the event list in the cache.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.rate_limiter import limiter
from app.services.settings import get_decrypted_setting

from app.plugins.nl_search import budget, cache, orchestrator
from app.plugins.nl_search.prompts import load_system_prompt
from app.plugins.nl_search.providers import make_provider
from app.plugins.nl_search.providers.base import ProviderError
from app.plugins.nl_search.service import (
    AuthRequiredError,
    OverCapacityError,
    acquire_concurrency_slot,
    auth_gate,
    format_sse,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/nl-search", tags=["nl_search"])

_ANON_RATE = "3/minute;30/day"


class NlSearchQuery(BaseModel):
    """Request body — single user-typed natural-language question."""

    query: str = Field(min_length=1, max_length=4000)
    lang: str | None = Field(default=None, max_length=8)


def _err_event(code: str, message: str) -> str:
    return format_sse("error", {"code": code, "message": message}) + format_sse(
        "done", {}
    )


@router.post("/query")
@limiter.limit(_ANON_RATE)
async def nl_search_query(
    body: NlSearchQuery,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> StreamingResponse:
    """Stream a tool-grounded answer to a public natural-language query.

    Output: text/event-stream. Events:

    - ``status``  — phase/tool-call activity (``thinking``, ``tool_call``,
      ``tool_done``).
    - ``chunk``   — incremental answer text.
    - ``citations`` — final cleaned citation list.
    - ``error``   — ``{code, message}`` on any pre-flight failure.
    - ``done``    — terminal marker; the browser closes the stream.
    """
    user = getattr(request.state, "user", None)

    # Pre-flight gates that should raise normal HTTP errors (status code
    # carries meaning to the browser even if no SSE arrives).
    try:
        await auth_gate(db, user_present=user is not None)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    # Length cap on the input (defence in depth — Pydantic already
    # enforces 4000 max). Soft cap from settings can be tighter.
    raw_max = (await get_decrypted_setting(db, "nl_search_max_input_chars")).strip() or "500"
    try:
        max_chars = max(50, int(raw_max))
    except ValueError:
        max_chars = 500
    if len(body.query) > max_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Query exceeds {max_chars}-character soft cap.",
        )

    if await budget.is_over_cap(db):
        raise HTTPException(
            status_code=503,
            detail="Daily budget exhausted; try again tomorrow.",
        )

    # Resolve plugin-level config up front so we can build the cache key
    # without an additional DB round-trip later.
    provider_kind = (
        await get_decrypted_setting(db, "nl_search_provider")
    ).strip().lower() or "ollama"
    model = (await get_decrypted_setting(db, "nl_search_model")).strip() or (
        "claude-sonnet-4-6" if provider_kind == "anthropic" else "llama3.1"
    )
    corpus_id = (await get_decrypted_setting(db, "nl_search_corpus_id")).strip()
    cache_ttl = int(
        (await get_decrypted_setting(db, "nl_search_cache_ttl_minutes")).strip() or "60"
    )
    timeout_s = float(
        (await get_decrypted_setting(db, "nl_search_query_timeout_s")).strip() or "30"
    )
    max_rounds = int(
        (await get_decrypted_setting(db, "nl_search_max_tool_rounds")).strip() or "6"
    )

    cache_key = cache.build_key(
        corpus_id=corpus_id,
        provider=provider_kind,
        model=model,
        query=body.query,
    )
    cached_events = await cache.lookup(db, cache_key)
    if cached_events is not None:
        logger.info("nl_search_cache_hit", key=cache_key)

        async def replay() -> AsyncGenerator[str, None]:
            for event in cached_events:
                name = event.get("name")
                data = event.get("data") or {}
                if isinstance(name, str):
                    yield format_sse(name, data)

        await db.commit()  # persist the hits++ from cache.lookup
        return _stream(replay())

    # Resolve the synthetic MCP context from the configured corpus.
    ctx = await orchestrator.build_synthetic_ctx(db, corpus_id=corpus_id)
    if ctx is None:
        async def err_stream() -> AsyncGenerator[str, None]:
            yield _err_event(
                "CORPUS_NOT_CONFIGURED",
                "An Admin must select an MCP corpus in Settings → NL search.",
            )

        return _stream(err_stream())

    system_prompt = load_system_prompt(body.lang or "en")

    try:
        provider = await make_provider(db, system_prompt=system_prompt)
    except ProviderError as exc:
        async def err_stream() -> AsyncGenerator[str, None]:
            yield _err_event("PROVIDER_MISCONFIGURED", str(exc))

        return _stream(err_stream())

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async with acquire_concurrency_slot(db):
                emitted: list[dict[str, Any]] = []
                final_result: orchestrator.OrchestratorResult | None = None

                async for ev in orchestrator.run(
                    db=db,
                    provider=provider,
                    provider_kind=provider_kind,
                    ctx=ctx,
                    query=body.query,
                    system_prompt=system_prompt,
                    timeout_s=timeout_s,
                    max_rounds=max_rounds,
                ):
                    if isinstance(ev, orchestrator.OrchestratorEvent):
                        emitted.append({"name": ev.name, "data": ev.data})
                        yield format_sse(ev.name, ev.data)
                    else:
                        final_result = ev

                if final_result is not None:
                    eur = budget.estimate_eur(
                        provider=provider_kind,
                        model=model,
                        usage=final_result.total_usage,
                    )
                    await budget.record_spend(db, eur=eur)
                    if final_result.error is None:
                        await cache.store(
                            db,
                            key=cache_key,
                            events=emitted,
                            ttl_minutes=cache_ttl,
                        )
                    await db.commit()
        except OverCapacityError as exc:
            yield _err_event("OVER_CAPACITY", str(exc))
        except Exception as exc:  # noqa: BLE001 — last-resort SSE error
            logger.exception("nl_search_unhandled_error")
            yield _err_event("INTERNAL_ERROR", str(exc))

    return _stream(event_stream())


def _stream(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
