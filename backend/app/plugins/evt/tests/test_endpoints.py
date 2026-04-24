"""Tests for the native EVT Viewer plugin.

The plugin exposes two public endpoints consumed by the EVT nginx
container. Both require the collection to be *published and public*;
the document endpoint additionally validates the filename against
path-traversal and XML-extension rules.

No authentication is required on these routes — they are intentionally
public ([pub]) so the EVT container can proxy without credentials.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _mk_collection(
    db: AsyncSession,
    *,
    slug: str = "magna-cartha",
    title: str = "Magna Cartha",
    status: CollectionStatus = CollectionStatus.published,
    is_public: bool = True,
) -> Collection:
    col = Collection(
        slug=slug,
        title=title,
        description="Test edition",
        status=status,
        is_public=is_public,
    )
    db.add(col)
    await db.flush()
    return col


# ── evt-config happy path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evt_config_published_public_returns_200(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb: AsyncMock,
) -> None:
    await _mk_collection(db_session, slug="magna-cartha", title="Magna Cartha")
    mock_existdb.list_collection.return_value = ["doc_a.xml", "doc_b.xml"]

    res = await client_with_existdb.get(
        "/api/v1/public/collections/magna-cartha/evt-config"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["projectName"] == "Magna Cartha"
    assert body["defaultEdition"] == "diplomatic"
    # First file (alphabetical) must be referenced in dataUrl.
    assert body["dataUrl"] == "data/doc_a.xml"
    # Cache-Control header is part of the public contract for the EVT
    # nginx proxy — assert it is set.
    assert "public" in res.headers.get("cache-control", "").lower()


@pytest.mark.asyncio
async def test_evt_config_empty_collection_has_empty_data_url(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb: AsyncMock,
) -> None:
    await _mk_collection(db_session, slug="empty-set")
    mock_existdb.list_collection.return_value = []

    res = await client_with_existdb.get(
        "/api/v1/public/collections/empty-set/evt-config"
    )
    assert res.status_code == 200
    assert res.json()["dataUrl"] == ""


@pytest.mark.asyncio
async def test_evt_config_non_public_returns_404(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _mk_collection(
        db_session, slug="private-set", is_public=False,
    )
    res = await client_with_existdb.get(
        "/api/v1/public/collections/private-set/evt-config"
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_evt_config_draft_returns_404(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _mk_collection(
        db_session, slug="draft-set", status=CollectionStatus.draft,
    )
    res = await client_with_existdb.get(
        "/api/v1/public/collections/draft-set/evt-config"
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_evt_config_unknown_slug_returns_404(
    client_with_existdb: AsyncClient,
) -> None:
    res = await client_with_existdb.get(
        "/api/v1/public/collections/does-not-exist/evt-config"
    )
    assert res.status_code == 404


# ── document/raw happy path and validation ───────────────────────────────────


@pytest.mark.asyncio
async def test_document_raw_returns_xml(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb: AsyncMock,
) -> None:
    await _mk_collection(db_session, slug="magna-cartha")
    mock_existdb.get_document.return_value = b"<TEI>hello</TEI>"

    res = await client_with_existdb.get(
        "/api/v1/public/collections/magna-cartha/documents/chap1.xml/raw"
    )
    assert res.status_code == 200
    assert res.content == b"<TEI>hello</TEI>"
    assert "application/xml" in res.headers["content-type"]


@pytest.mark.asyncio
async def test_document_raw_rejects_path_traversal(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _mk_collection(db_session, slug="magna-cartha")
    # FastAPI parses the path so "../" is resolved before reaching the
    # handler — either way the filename regex rejects it at the
    # service layer.
    res = await client_with_existdb.get(
        "/api/v1/public/collections/magna-cartha/documents/..%2Fetc%2Fpasswd/raw"
    )
    # 400 (service validation) or 404 (router path matching) are both
    # acceptable — we just require "not 200 with file content".
    assert res.status_code in {400, 404, 422}


@pytest.mark.asyncio
async def test_document_raw_rejects_non_xml_extension(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _mk_collection(db_session, slug="magna-cartha")
    res = await client_with_existdb.get(
        "/api/v1/public/collections/magna-cartha/documents/evil.exe/raw"
    )
    # DomainValidationError maps to 422 via the global handler.
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_FILENAME"


@pytest.mark.asyncio
async def test_document_raw_rejects_leading_dot(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _mk_collection(db_session, slug="magna-cartha")
    res = await client_with_existdb.get(
        "/api/v1/public/collections/magna-cartha/documents/.hidden.xml/raw"
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_FILENAME"


@pytest.mark.asyncio
async def test_document_raw_private_collection_returns_404(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _mk_collection(db_session, slug="private-set", is_public=False)
    res = await client_with_existdb.get(
        "/api/v1/public/collections/private-set/documents/doc1.xml/raw"
    )
    assert res.status_code == 404
