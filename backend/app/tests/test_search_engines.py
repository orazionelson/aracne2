"""Tests for the search engine management endpoints.

Management tests use the standard ``client`` fixture (Postgres-only CRUD).
Public search tests patch ``app.services.search_engines.existdb_client``.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_engine import SearchEngine
from app.models.user import User
from app.tests.conftest import (
    DESIGNER_PASSWORD,
    DESIGNER_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_engine(db_session: AsyncSession, seeded_designer: User) -> SearchEngine:
    engine = SearchEngine(
        slug="test-engine",
        title="Test Engine",
        created_by=seeded_designer.id,
    )
    db_session.add(engine)
    await db_session.flush()
    return engine


# ── List public collections ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_public_collections_as_designer(
    client: AsyncClient, seeded_designer: User
) -> None:
    """Designer can list published+public collections available for assignment."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        "/api/v1/search-engines/public-collections", headers=_auth(token)
    )
    assert res.status_code == 200
    assert "data" in res.json()


@pytest.mark.asyncio
async def test_list_public_collections_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        "/api/v1/search-engines/public-collections", headers=_auth(token)
    )
    assert res.status_code == 403


# ── CRUD ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_search_engines_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_engine: SearchEngine
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get("/api/v1/search-engines", headers=_auth(token))
    assert res.status_code == 200
    slugs = [e["slug"] for e in res.json()["data"]]
    assert "test-engine" in slugs


@pytest.mark.asyncio
async def test_list_search_engines_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/search-engines", headers=_auth(token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_create_search_engine_as_designer(
    client: AsyncClient, seeded_designer: User
) -> None:
    """Designer can create a new search engine."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/search-engines",
        headers=_auth(token),
        json={"slug": "new-engine", "title": "New Engine"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["slug"] == "new-engine"


@pytest.mark.asyncio
async def test_get_search_engine_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_engine: SearchEngine
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        f"/api/v1/search-engines/{seeded_engine.slug}", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["data"]["slug"] == seeded_engine.slug


@pytest.mark.asyncio
async def test_update_search_engine_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_engine: SearchEngine
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.put(
        f"/api/v1/search-engines/{seeded_engine.slug}",
        headers=_auth(token),
        json={"title": "Updated Engine"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "Updated Engine"


@pytest.mark.asyncio
async def test_delete_search_engine_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_engine: SearchEngine
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.delete(
        f"/api/v1/search-engines/{seeded_engine.slug}", headers=_auth(token)
    )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_clear_cache(
    client: AsyncClient, seeded_designer: User, seeded_engine: SearchEngine
) -> None:
    """Clearing cache on an engine with no cached results returns 0 deleted."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        f"/api/v1/search-engines/{seeded_engine.slug}/cache/clear",
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] == 0


# ── Embed logs ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_embed_logs(
    client: AsyncClient, seeded_designer: User, seeded_engine: SearchEngine
) -> None:
    """A new search engine has no embed logs."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        f"/api/v1/search-engines/{seeded_engine.slug}/embed-logs",
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"] == []


# ── Public search (eXist-db patched) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_public_endpoint_with_no_collections(
    client: AsyncClient, seeded_engine: SearchEngine
) -> None:
    """Full-text search on an engine with no collections returns empty results."""
    # No eXist-db call is made when there are no linked collections
    res = await client.get(
        f"/api/v1/search-engines/{seeded_engine.slug}/search?q=test"
    )
    assert res.status_code == 200
    assert res.json()["data"]["results"] == []


@pytest.mark.asyncio
async def test_advanced_search_public_endpoint_with_no_collections(
    client: AsyncClient, seeded_engine: SearchEngine
) -> None:
    """Advanced search on an engine with no collections returns empty results."""
    res = await client.get(
        f"/api/v1/search-engines/{seeded_engine.slug}/advanced-search?element=persName"
    )
    assert res.status_code == 200
    assert res.json()["data"]["results"] == []


@pytest.mark.asyncio
async def test_search_nonexistent_engine_returns_404(client: AsyncClient) -> None:
    res = await client.get(
        "/api/v1/search-engines/does-not-exist/search?q=test"
    )
    assert res.status_code == 404
