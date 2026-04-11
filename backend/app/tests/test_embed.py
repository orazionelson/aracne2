"""Tests for the embed widget endpoints (/{slug}/widget.js, /{slug}/search, etc.).

widget.js only reads the DB (no eXist-db).
search/advanced-search delegate to search_engines.run_search / run_advanced_search,
which use existdb_client; those are tested with no linked collections so no
eXist-db call is made.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_engine import SearchEngine
from app.models.user import User


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def embed_engine(db_session: AsyncSession, seeded_designer: User) -> SearchEngine:
    """A search engine with embed_enabled=True."""
    engine = SearchEngine(
        slug="embed-test",
        title="Embed Test Engine",
        created_by=seeded_designer.id,
        embed_enabled=True,
    )
    db_session.add(engine)
    await db_session.flush()
    return engine


@pytest_asyncio.fixture
async def no_embed_engine(db_session: AsyncSession, seeded_designer: User) -> SearchEngine:
    """A search engine with embed_enabled=False (widget returns 404)."""
    engine = SearchEngine(
        slug="no-embed",
        title="No Embed Engine",
        created_by=seeded_designer.id,
        embed_enabled=False,
    )
    db_session.add(engine)
    await db_session.flush()
    return engine


# ── widget.js ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_widget_js_serves_js_for_existing_engine(
    client: AsyncClient, embed_engine: SearchEngine
) -> None:
    """widget.js returns JavaScript for an embed-enabled engine."""
    res = await client.get(f"/api/v1/embed/{embed_engine.slug}/widget.js")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]
    assert "aracne2" in res.text.lower()


@pytest.mark.asyncio
async def test_widget_js_returns_404_for_disabled_engine(
    client: AsyncClient, no_embed_engine: SearchEngine
) -> None:
    """widget.js returns 404 when embed is not enabled for the engine."""
    res = await client.get(f"/api/v1/embed/{no_embed_engine.slug}/widget.js")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_widget_js_returns_404_for_unknown_engine(
    client: AsyncClient,
) -> None:
    """widget.js returns 404 for a slug that does not exist."""
    res = await client.get("/api/v1/embed/nonexistent/widget.js")
    assert res.status_code == 404


# ── Embed search (no collections → no eXist-db call) ─────────────────────────


@pytest.mark.asyncio
async def test_embed_search_returns_empty_results(
    client: AsyncClient, embed_engine: SearchEngine
) -> None:
    """Embed search on an engine with no linked collections returns empty results."""
    res = await client.get(
        f"/api/v1/embed/{embed_engine.slug}/search?q=test"
    )
    assert res.status_code == 200
    assert res.json()["data"]["results"] == []


@pytest.mark.asyncio
async def test_embed_advanced_search_returns_empty_results(
    client: AsyncClient, embed_engine: SearchEngine
) -> None:
    """Embed advanced search on an engine with no collections returns empty results."""
    res = await client.get(
        f"/api/v1/embed/{embed_engine.slug}/advanced-search?element=persName"
    )
    assert res.status_code == 200
    assert res.json()["data"]["results"] == []


@pytest.mark.asyncio
async def test_embed_search_on_disabled_engine_returns_404(
    client: AsyncClient, no_embed_engine: SearchEngine
) -> None:
    """Embed search returns 404 when the engine has embed_enabled=False."""
    res = await client.get(
        f"/api/v1/embed/{no_embed_engine.slug}/search?q=test"
    )
    assert res.status_code == 404
