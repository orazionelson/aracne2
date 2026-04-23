"""Tests for the native OAI-PMH provider plugin.

Covers the verb dispatcher at service level (no real eXist-db, mock
client) and one end-to-end router call to confirm the endpoint is
wired. We deliberately skip testing full record payload generation —
that depends on TEI header content and is better exercised with real
documents during integration testing.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.plugins._native.oai_pmh import service

_OAI_NS = "http://www.openarchives.org/OAI/2.0/"
_BASE_URL = "http://testserver/api/v1/oai"


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _mk_collection(
    db: AsyncSession,
    *,
    slug: str,
    title: str = "Sample",
    is_public: bool = True,
    status: CollectionStatus = CollectionStatus.published,
) -> Collection:
    col = Collection(
        slug=slug,
        title=title,
        description=f"Description of {title}",
        status=status,
        is_public=is_public,
        published_at=datetime.now(UTC) if status == CollectionStatus.published else None,
    )
    db.add(col)
    await db.flush()
    return col


def _first_child_tag(xml: str, tag: str) -> ET.Element | None:
    """Return the first element with the given local name anywhere in the tree."""
    root = ET.fromstring(xml)
    return root.find(f".//{{{_OAI_NS}}}{tag}")


def _error_code(xml: str) -> str | None:
    root = ET.fromstring(xml)
    err = root.find(f"{{{_OAI_NS}}}error")
    return err.attrib.get("code") if err is not None else None


async def _dispatch(
    db: AsyncSession,
    existdb: AsyncMock,
    **kwargs: object,
) -> str:
    """Shortcut that fills in the full dispatch keyword set with Nones."""
    defaults: dict[str, object | None] = {
        "base_url": _BASE_URL,
        "verb": None,
        "identifier": None,
        "metadata_prefix": None,
        "set_spec": None,
        "from_date": None,
        "until": None,
        "resumption_token": None,
    }
    defaults.update(kwargs)
    defaults["db"] = db
    defaults["existdb"] = existdb
    return await service.dispatch(**defaults)  # type: ignore[arg-type]


# ── Missing / invalid verbs ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_verb_returns_bad_verb(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(db_session, mock_existdb, verb=None)
    assert _error_code(xml) == "badVerb"


@pytest.mark.asyncio
async def test_unknown_verb_returns_bad_verb(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(db_session, mock_existdb, verb="Harvest")
    assert _error_code(xml) == "badVerb"


# ── Identify ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_identify_returns_envelope(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(db_session, mock_existdb, verb="Identify")
    assert _first_child_tag(xml, "Identify") is not None
    # Required elements per OAI-PMH 2.0.
    assert _first_child_tag(xml, "repositoryName") is not None
    assert _first_child_tag(xml, "baseURL") is not None
    assert _first_child_tag(xml, "protocolVersion") is not None
    assert _first_child_tag(xml, "adminEmail") is not None
    assert _first_child_tag(xml, "earliestDatestamp") is not None
    assert _first_child_tag(xml, "deletedRecord") is not None
    assert _first_child_tag(xml, "granularity") is not None


# ── ListMetadataFormats ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_metadata_formats_advertises_oai_dc(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(db_session, mock_existdb, verb="ListMetadataFormats")
    root = ET.fromstring(xml)
    prefixes = [
        p.text
        for p in root.findall(f".//{{{_OAI_NS}}}metadataPrefix")
    ]
    assert prefixes == ["oai_dc"]


@pytest.mark.asyncio
async def test_list_metadata_formats_bad_identifier(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(
        db_session, mock_existdb,
        verb="ListMetadataFormats",
        identifier="not-a-valid-oai-id",
    )
    assert _error_code(xml) == "idDoesNotExist"


# ── ListSets ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_sets_empty_returns_no_set_hierarchy(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(db_session, mock_existdb, verb="ListSets")
    assert _error_code(xml) == "noSetHierarchy"


@pytest.mark.asyncio
async def test_list_sets_exposes_published_public_collections(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    await _mk_collection(db_session, slug="col-a", title="Collection A")
    await _mk_collection(db_session, slug="col-b", title="Collection B")
    # Drafts are excluded.
    await _mk_collection(
        db_session, slug="col-draft", status=CollectionStatus.draft,
    )
    # Private collections are excluded.
    await _mk_collection(db_session, slug="col-private", is_public=False)

    xml = await _dispatch(db_session, mock_existdb, verb="ListSets")
    root = ET.fromstring(xml)
    slugs = [
        s.text
        for s in root.findall(f".//{{{_OAI_NS}}}setSpec")
    ]
    assert set(slugs) == {"col-a", "col-b"}


# ── ListIdentifiers / ListRecords argument validation ────────────────────────


@pytest.mark.asyncio
async def test_list_identifiers_without_prefix_is_bad_argument(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(db_session, mock_existdb, verb="ListIdentifiers")
    assert _error_code(xml) == "badArgument"


@pytest.mark.asyncio
async def test_list_identifiers_unknown_prefix_is_cannot_disseminate(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(
        db_session, mock_existdb,
        verb="ListIdentifiers",
        metadata_prefix="mods",
    )
    assert _error_code(xml) == "cannotDisseminateFormat"


@pytest.mark.asyncio
async def test_list_records_invalid_resumption_token(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(
        db_session, mock_existdb,
        verb="ListRecords",
        resumption_token="not-base64-nor-json",
    )
    assert _error_code(xml) == "badResumptionToken"


# ── GetRecord argument validation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_record_without_identifier_is_bad_argument(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(db_session, mock_existdb, verb="GetRecord")
    assert _error_code(xml) == "badArgument"


@pytest.mark.asyncio
async def test_get_record_without_prefix_is_bad_argument(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(
        db_session, mock_existdb,
        verb="GetRecord",
        identifier="oai:testserver:col-a/doc1.xml",
    )
    assert _error_code(xml) == "badArgument"


@pytest.mark.asyncio
async def test_get_record_unknown_prefix_is_cannot_disseminate(
    db_session: AsyncSession, mock_existdb: AsyncMock,
) -> None:
    xml = await _dispatch(
        db_session, mock_existdb,
        verb="GetRecord",
        identifier="oai:testserver:col-a/doc1.xml",
        metadata_prefix="mods",
    )
    assert _error_code(xml) == "cannotDisseminateFormat"


# ── End-to-end router smoke test ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_router_mounted_and_responds_to_identify(
    client_with_existdb: AsyncClient,
) -> None:
    """Confirm the endpoint is reachable and returns valid OAI XML."""
    res = await client_with_existdb.get("/api/v1/oai?verb=Identify")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    assert f"{{{_OAI_NS}}}Identify" in res.text or "<Identify>" in res.text


@pytest.mark.asyncio
async def test_router_no_verb_returns_bad_verb_but_200(
    client_with_existdb: AsyncClient,
) -> None:
    """OAI-PMH convention: errors are returned as 200 OK with <error> element,
    not HTTP 4xx."""
    res = await client_with_existdb.get("/api/v1/oai")
    assert res.status_code == 200
    assert "badVerb" in res.text
