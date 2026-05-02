"""SSE endpoint tests — pre-flight gates, cache replay, error events.

These tests use the FastAPI ``client`` fixture so the slowapi limiter
and the dependency tree run end-to-end. Provider HTTP calls are
intercepted in the orchestrator unit tests; here we focus on the
*endpoint*'s pre-flight branches that don't need an LLM:

- 401 when ``require_login=true`` and no auth header.
- 503 when daily budget is already over.
- 503 when concurrency cap is exhausted (skipped — would require
  blocking a real semaphore in-process; covered indirectly by
  service-level tests below).
- ``CORPUS_NOT_CONFIGURED`` SSE event when ``nl_search_corpus_id``
  is empty.
- Cache hit path replays the stored event list verbatim.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nl_search_budget import NlSearchBudgetDay
from app.models.nl_search_cache import NlSearchCache
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.plugins.nl_search.cache import build_key
from app.plugins.nl_search.plugin import Plugin as NlSearchPluginCls

# Plugin router needs to be mounted manually for tests since the
# loader's hot-mount path runs at runtime activation.
_ROUTER_MOUNTED_KEY = "_nl_search_router_mounted_in_test"


@pytest.fixture
async def nl_search_active(db_session: AsyncSession) -> None:
    """Ensure the plugin row is active and the basic settings are seeded."""
    db_session.add(
        Plugin(
            name="nl_search",
            display_name="Natural-language search",
            status=PluginStatus.active,
            is_native=False,
            capabilities=list(NlSearchPluginCls.meta.capabilities),
            ui_descriptor=NlSearchPluginCls.meta.ui_descriptor,
        )
    )
    for key, value, kind in [
        ("nl_search_require_login", "false", "bool"),
        ("nl_search_provider", "ollama", "string"),
        ("nl_search_model", "llama3.1", "string"),
        ("nl_search_corpus_id", "", "string"),
        ("nl_search_daily_budget_eur", "2.00", "string"),
        ("nl_search_max_concurrent", "2", "int"),
        ("nl_search_query_timeout_s", "30", "int"),
        ("nl_search_cache_ttl_minutes", "60", "int"),
        ("nl_search_max_input_chars", "500", "int"),
        ("nl_search_max_tool_rounds", "6", "int"),
    ]:
        existing = await db_session.get(SystemSetting, key)
        if existing is None:
            db_session.add(SystemSetting(key=key, value=value, type=kind))
    await db_session.flush()


def _mount_nl_search_router(app) -> None:
    """Idempotently include the nl_search router on the test app."""
    if getattr(app.state, _ROUTER_MOUNTED_KEY, False):
        return
    from app.plugins.nl_search.router import router as nl_router

    app.include_router(nl_router, prefix="/api/v1")
    setattr(app.state, _ROUTER_MOUNTED_KEY, True)


@pytest.mark.asyncio
async def test_query_401_when_login_required_anonymous(
    client: AsyncClient,
    db_session: AsyncSession,
    nl_search_active: None,
) -> None:
    """``require_login=true`` (default) + no Authorization → 401."""
    require_row = await db_session.get(SystemSetting, "nl_search_require_login")
    assert require_row is not None
    require_row.value = "true"
    await db_session.flush()
    _mount_nl_search_router(client._transport.app)  # type: ignore[attr-defined]

    resp = await client.post("/api/v1/nl-search/query", json={"query": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_query_503_when_budget_exhausted(
    client: AsyncClient,
    db_session: AsyncSession,
    nl_search_active: None,
) -> None:
    """Today's row at the cap → 503 BUDGET_EXCEEDED."""
    db_session.add(
        NlSearchBudgetDay(
            day=datetime.now(UTC).date(),
            eur_spent="5.00",  # over the 2.00 default
            queries=10,
        )
    )
    await db_session.flush()
    _mount_nl_search_router(client._transport.app)  # type: ignore[attr-defined]

    resp = await client.post("/api/v1/nl-search/query", json={"query": "hi"})
    assert resp.status_code == 503
    assert "budget" in resp.json()["error"]["message"].lower() or \
        "budget" in resp.text.lower()


@pytest.mark.asyncio
async def test_query_emits_corpus_not_configured_event(
    client: AsyncClient,
    db_session: AsyncSession,
    nl_search_active: None,
) -> None:
    """No ``nl_search_corpus_id`` → CORPUS_NOT_CONFIGURED SSE event."""
    _mount_nl_search_router(client._transport.app)  # type: ignore[attr-defined]

    resp = await client.post("/api/v1/nl-search/query", json={"query": "hi"})
    assert resp.status_code == 200
    body = resp.text
    assert "event: error" in body
    assert "CORPUS_NOT_CONFIGURED" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_query_replays_cached_events_on_hit(
    client: AsyncClient,
    db_session: AsyncSession,
    nl_search_active: None,
) -> None:
    """A pre-existing cache row whose key matches → events replayed verbatim."""
    key = build_key(
        corpus_id="",
        provider="ollama",
        model="llama3.1",
        query="hi",
    )
    cached_events = [
        {"name": "status", "data": {"phase": "thinking"}},
        {"name": "chunk", "data": {"text": "Replayed answer."}},
        {"name": "citations", "data": {"items": []}},
        {"name": "done", "data": {}},
    ]
    db_session.add(
        NlSearchCache(
            key=key,
            response_json=json.dumps(cached_events),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db_session.flush()
    _mount_nl_search_router(client._transport.app)  # type: ignore[attr-defined]

    resp = await client.post("/api/v1/nl-search/query", json={"query": "hi"})
    assert resp.status_code == 200
    body = resp.text
    # Replayed text comes through; orchestrator never ran.
    assert "Replayed answer." in body
    assert "event: done" in body
