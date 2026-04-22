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


# ── Content negotiation (LOD.3b) ──────────────────────────────────────────────


async def _get_public(client: AsyncClient, slug: str, accept: str | None) -> object:
    """Helper: patch existdb + issue a GET with a specific Accept header."""
    headers = {"accept": accept} if accept else None
    with patch("app.services.public_view.existdb_client") as mock_db:
        mock_db.xquery = AsyncMock(return_value=b"<docs/>")
        mock_db.list_collection = AsyncMock(return_value=[])
        mock_db.col_path = lambda slug: f"/db/aracne2/collections/{slug}"
        return await client.get(
            f"/api/v1/public/collections/{slug}", headers=headers
        )


@pytest.mark.asyncio
async def test_collection_default_accept_returns_json_envelope(
    client: AsyncClient, public_collection: Collection
) -> None:
    """SPA behaviour preserved: no / wildcard / application/json Accept
    still produces the historical {data: PublicCollectionDetail} envelope."""
    for accept in (None, "*/*", "application/json"):
        res = await _get_public(client, public_collection.slug, accept)
        assert res.status_code == 200, f"Accept={accept!r}"  # type: ignore[union-attr]
        assert "application/json" in res.headers["content-type"]  # type: ignore[union-attr]
        assert res.json()["data"]["slug"] == public_collection.slug  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_collection_accept_turtle_returns_turtle(
    client: AsyncClient, public_collection: Collection
) -> None:
    res = await _get_public(client, public_collection.slug, "text/turtle")
    assert res.status_code == 200  # type: ignore[union-attr]
    assert "text/turtle" in res.headers["content-type"]  # type: ignore[union-attr]
    body = res.text  # type: ignore[union-attr]
    # Sanity: the Turtle lists the collection as a schema:CreativeWork with
    # the configured title as its schema:name.
    assert "CreativeWork" in body
    assert public_collection.title in body


@pytest.mark.asyncio
async def test_collection_accept_rdf_xml_returns_rdf_xml(
    client: AsyncClient, public_collection: Collection
) -> None:
    res = await _get_public(client, public_collection.slug, "application/rdf+xml")
    assert res.status_code == 200  # type: ignore[union-attr]
    assert "application/rdf+xml" in res.headers["content-type"]  # type: ignore[union-attr]
    assert "<rdf:RDF" in res.text  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_collection_accept_json_ld_returns_json_ld(
    client: AsyncClient, public_collection: Collection
) -> None:
    import json as _json

    res = await _get_public(client, public_collection.slug, "application/ld+json")
    assert res.status_code == 200  # type: ignore[union-attr]
    assert "application/ld+json" in res.headers["content-type"]  # type: ignore[union-attr]
    # Must be valid JSON — the whole point of the format.
    parsed = _json.loads(res.text)  # type: ignore[union-attr]
    assert parsed, "empty JSON-LD payload"


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


# ── Document content negotiation (LOD.3c) ─────────────────────────────────────


async def _get_public_document(
    client: AsyncClient,
    slug: str,
    filename: str,
    accept: str | None,
) -> object:
    """GET the document endpoint with a specific Accept header, patching
    the existdb calls that the content-neg branch does NOT hit (the HTML
    branch still needs them, so we patch both to be safe)."""
    headers = {"accept": accept} if accept else None
    minimal_tei = b"""<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>
  <publicationStmt><p>Test</p></publicationStmt>
  <sourceDesc><p>Test</p></sourceDesc></fileDesc></teiHeader>
  <text><body><div><p>Hello</p></div></body></text>
</TEI>"""
    with patch("app.services.public_view.existdb_client") as mock_db:
        mock_db.get_document = AsyncMock(return_value=minimal_tei)
        mock_db.xquery = AsyncMock(return_value=b"<docs/>")
        mock_db.list_collection = AsyncMock(return_value=[filename])
        mock_db.col_path = lambda slug: f"/db/aracne2/collections/{slug}"
        return await client.get(
            f"/api/v1/public/collections/{slug}/documents/{filename}",
            headers=headers,
        )


@pytest.mark.asyncio
async def test_document_default_accept_returns_html(
    client: AsyncClient, public_collection: Collection
) -> None:
    """Existing behaviour preserved: default Accept still serves HTML
    for the iframe."""
    for accept in (None, "text/html", "*/*"):
        res = await _get_public_document(
            client, public_collection.slug, "test.xml", accept
        )
        assert res.status_code == 200, f"Accept={accept!r}"  # type: ignore[union-attr]
        assert "text/html" in res.headers["content-type"]  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_document_accept_turtle_returns_turtle_with_isPartOf(
    client: AsyncClient, public_collection: Collection
) -> None:
    res = await _get_public_document(
        client, public_collection.slug, "test.xml", "text/turtle"
    )
    assert res.status_code == 200  # type: ignore[union-attr]
    assert "text/turtle" in res.headers["content-type"]  # type: ignore[union-attr]
    body = res.text  # type: ignore[union-attr]
    # Spot-check: the collection URI appears as isPartOf of the document.
    assert public_collection.slug in body
    assert "isPartOf" in body or "schema:isPartOf" in body


@pytest.mark.asyncio
async def test_document_accept_json_ld_returns_json_ld(
    client: AsyncClient, public_collection: Collection
) -> None:
    import json as _json

    res = await _get_public_document(
        client, public_collection.slug, "test.xml", "application/ld+json"
    )
    assert res.status_code == 200  # type: ignore[union-attr]
    assert "application/ld+json" in res.headers["content-type"]  # type: ignore[union-attr]
    _json.loads(res.text)  # type: ignore[union-attr]  # must parse
