"""Tests for public view endpoints (/public/collections/*).

eXist-db calls inside public_view.py use the module-level singleton
``existdb_client``, so they are patched directly via unittest.mock.patch.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def public_collection(db_session: AsyncSession) -> Collection:
    """A published, public collection accessible without authentication."""
    col = Collection(
        slug="public-test",
        title="Public Test Collection",
        status=CollectionStatus.published,
        is_public=True,
    )
    db_session.add(col)
    await db_session.flush()
    return col


# ── Collection detail ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_public_collection_returns_200(
    client: AsyncClient, public_collection: Collection
) -> None:
    """Public collection detail returns metadata and empty document list."""
    with patch("app.services.public_view.existdb_client") as mock_db:
        mock_db.xquery = AsyncMock(return_value=b"<docs/>")
        mock_db.list_collection = AsyncMock(return_value=[])
        mock_db.col_path = lambda slug: f"/db/aracne2/collections/{slug}"
        res = await client.get(
            f"/api/v1/public/collections/{public_collection.slug}"
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["slug"] == public_collection.slug
    assert data["title"] == public_collection.title


@pytest.mark.asyncio
async def test_get_nonexistent_public_collection_returns_404(
    client: AsyncClient,
) -> None:
    """Requesting a non-existent (or private) collection returns 404."""
    res = await client.get("/api/v1/public/collections/does-not-exist")
    assert res.status_code == 404


# ── Document render ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_public_document_returns_200(
    client: AsyncClient, public_collection: Collection
) -> None:
    """Public document renders to HTML via the built-in XSLT stylesheet."""
    minimal_tei = b"""<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>
  <publicationStmt><p>Test</p></publicationStmt>
  <sourceDesc><p>Test</p></sourceDesc></fileDesc></teiHeader>
  <text><body><div><p>Hello world</p></div></body></text>
</TEI>"""
    with patch("app.services.public_view.existdb_client") as mock_db:
        mock_db.get_document = AsyncMock(return_value=minimal_tei)
        mock_db.col_path = lambda slug: f"/db/aracne2/collections/{slug}"
        res = await client.get(
            f"/api/v1/public/collections/{public_collection.slug}/documents/test.xml"
        )
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


@pytest.mark.asyncio
async def test_get_public_document_not_found_returns_404(
    client: AsyncClient, public_collection: Collection
) -> None:
    """A document that eXist-db does not have returns 404."""
    from app.core.exceptions import NotFoundError

    with patch("app.services.public_view.existdb_client") as mock_db:
        mock_db.get_document = AsyncMock(
            side_effect=NotFoundError("Document not found.")
        )
        res = await client.get(
            f"/api/v1/public/collections/{public_collection.slug}/documents/missing.xml"
        )
    assert res.status_code == 404
