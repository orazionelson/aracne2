"""Tests for the TEI <zone> endpoints.

The zone endpoints rely on eXist-db for document storage.  All tests use the
``client_with_existdb`` fixture which overrides both the DB session and the
eXist-db client with an AsyncMock, so no real XML database is required.
"""

import xml.etree.ElementTree as ET

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.core.exceptions import NotFoundError
from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

# Minimal TEI document with one surface and no zones.
_TEI_WITH_SURFACE = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader/>
  <facsimile>
    <surface xml:id="f1r">
      <graphic url="media/carta_1r.jpg"/>
    </surface>
  </facsimile>
  <text><body><div><p>text</p></div></body></text>
</TEI>"""

# Same document but with two pre-existing zones on surface f1r.
_TEI_WITH_ZONES = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader/>
  <facsimile>
    <surface xml:id="f1r">
      <graphic url="media/carta_1r.jpg"/>
      <zone xml:id="z_f1r_1" ulx="10" uly="20" lrx="100" lry="50"/>
      <zone xml:id="z_f1r_2" ulx="200" uly="80" lrx="500" lry="130"/>
    </surface>
  </facsimile>
  <text><body><div><p>text</p></div></body></text>
</TEI>"""

# Document with no <facsimile> block at all.
_TEI_NO_FACSIMILE = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader/>
  <text><body><div><p>text</p></div></body></text>
</TEI>"""

_TEI_NS = "http://www.tei-c.org/ns/1.0"
_XML_NS = "http://www.w3.org/XML/1998/namespace"


@pytest_asyncio.fixture
async def assigned_collection(
    db_session: AsyncSession, seeded_user: User
) -> Collection:
    """A collection in 'assigned' state with seeded_user as the editor."""
    col = Collection(
        slug="zone-test-col",
        title="Zone Test Collection",
        status=CollectionStatus.assigned,
        editor_id=seeded_user.id,
    )
    db_session.add(col)
    await db_session.flush()
    return col


@pytest_asyncio.fixture
async def published_collection(
    db_session: AsyncSession, seeded_user: User
) -> Collection:
    col = Collection(
        slug="zone-pub-col",
        title="Zone Published Collection",
        status=CollectionStatus.published,
        editor_id=seeded_user.id,
    )
    db_session.add(col)
    await db_session.flush()
    return col


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _zones_url(slug: str, surface_id: str = "f1r") -> str:
    return f"/api/v1/collections/{slug}/documents/doc.xml/facsimile/{surface_id}/zones"


def _import_url(slug: str, surface_id: str = "f1r") -> str:
    return (
        f"/api/v1/collections/{slug}/documents/doc.xml/facsimile/{surface_id}/zones/import"
    )


def _count_zones(xml_bytes: bytes, surface_id: str = "f1r") -> int:
    """Parse *xml_bytes* and return the number of <zone> children on the surface."""
    root = ET.fromstring(xml_bytes)
    for surface in root.iter(f"{{{_TEI_NS}}}surface"):
        if surface.get(f"{{{_XML_NS}}}id") == surface_id:
            return len(list(surface.findall(f"{{{_TEI_NS}}}zone")))
    return 0


# ── Happy-path tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_zones_returns_empty_when_surface_has_no_zones(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """GET zones returns an empty list when the surface has no <zone> children."""
    mock_existdb.get_document.return_value = _TEI_WITH_SURFACE
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.get(_zones_url(assigned_collection.slug), headers=_auth(token))

    assert res.status_code == 200
    body = res.json()["data"]
    assert body["surface_id"] == "f1r"
    assert body["zones"] == []


@pytest.mark.asyncio
async def test_get_zones_returns_existing_zones(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """GET zones returns the correct zone data when <zone> elements exist."""
    mock_existdb.get_document.return_value = _TEI_WITH_ZONES
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.get(_zones_url(assigned_collection.slug), headers=_auth(token))

    assert res.status_code == 200
    zones = res.json()["data"]["zones"]
    assert len(zones) == 2
    assert zones[0]["xml_id"] == "z_f1r_1"
    assert zones[0]["ulx"] == 10
    assert zones[0]["uly"] == 20
    assert zones[0]["lrx"] == 100
    assert zones[0]["lry"] == 50
    assert zones[1]["xml_id"] == "z_f1r_2"


@pytest.mark.asyncio
async def test_put_zones_stores_zones_in_document(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """PUT zones writes the provided zones back to eXist-db."""
    mock_existdb.get_document.return_value = _TEI_WITH_SURFACE
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    payload = {
        "zones": [
            {"xml_id": "z_f1r_1", "ulx": 42, "uly": 120, "lrx": 310, "lry": 200},
        ]
    }
    res = await client_with_existdb.put(
        _zones_url(assigned_collection.slug), json=payload, headers=_auth(token)
    )

    assert res.status_code == 200
    body = res.json()["data"]
    assert len(body["zones"]) == 1
    assert body["zones"][0]["xml_id"] == "z_f1r_1"

    # Verify put_document was called and the written XML contains the zone.
    mock_existdb.put_document.assert_called_once()
    _slug, _filename, written_bytes = mock_existdb.put_document.call_args.args
    assert _count_zones(written_bytes, "f1r") == 1

    root = ET.fromstring(written_bytes)
    for surface in root.iter(f"{{{_TEI_NS}}}surface"):
        if surface.get(f"{{{_XML_NS}}}id") == "f1r":
            zone_el = surface.find(f"{{{_TEI_NS}}}zone")
            assert zone_el is not None
            assert zone_el.get(f"{{{_XML_NS}}}id") == "z_f1r_1"
            assert zone_el.get("ulx") == "42"


@pytest.mark.asyncio
async def test_put_zones_empty_list_removes_all_zones(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """PUT zones with an empty list removes all existing zones."""
    mock_existdb.get_document.return_value = _TEI_WITH_ZONES
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.put(
        _zones_url(assigned_collection.slug), json={"zones": []}, headers=_auth(token)
    )

    assert res.status_code == 200
    assert res.json()["data"]["zones"] == []

    _slug, _filename, written_bytes = mock_existdb.put_document.call_args.args
    assert _count_zones(written_bytes, "f1r") == 0


@pytest.mark.asyncio
async def test_import_zones_returns_201(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """POST zones/import stores zones and returns 201."""
    mock_existdb.get_document.return_value = _TEI_WITH_SURFACE
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    payload = {
        "zones": [
            {"xml_id": "z_f1r_1", "ulx": 5, "uly": 10, "lrx": 200, "lry": 100},
            {"xml_id": "z_f1r_2", "ulx": 210, "uly": 10, "lrx": 400, "lry": 100},
        ]
    }
    res = await client_with_existdb.post(
        _import_url(assigned_collection.slug), json=payload, headers=_auth(token)
    )

    assert res.status_code == 201
    assert len(res.json()["data"]["zones"]) == 2


# ── Error-case tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_zones_returns_404_for_unknown_surface(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """GET zones returns 404 when the surface_id does not exist in the document."""
    mock_existdb.get_document.return_value = _TEI_WITH_SURFACE
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.get(
        _zones_url(assigned_collection.slug, surface_id="nonexistent"),
        headers=_auth(token),
    )

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_zones_returns_404_when_document_missing(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """GET zones returns 404 when the document does not exist in eXist-db."""
    mock_existdb.get_document.side_effect = NotFoundError("Document not found")
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.get(_zones_url(assigned_collection.slug), headers=_auth(token))

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_put_zones_requires_write_access(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    published_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """PUT zones on a published collection is rejected with 403."""
    mock_existdb.get_document.return_value = _TEI_WITH_SURFACE
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.put(
        _zones_url(published_collection.slug),
        json={"zones": []},
        headers=_auth(token),
    )

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_get_zones_unauthenticated_returns_401(
    client_with_existdb: AsyncClient,
    assigned_collection: Collection,
) -> None:
    """Unauthenticated GET zones request is rejected with 401."""
    res = await client_with_existdb.get(_zones_url(assigned_collection.slug))
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_zones_returns_empty_when_facsimile_block_absent(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """GET zones returns an empty list (not 404) when no <facsimile> block exists."""
    mock_existdb.get_document.return_value = _TEI_NO_FACSIMILE
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.get(_zones_url(assigned_collection.slug), headers=_auth(token))

    assert res.status_code == 200
    body = res.json()["data"]
    assert body["zones"] == []


@pytest.mark.asyncio
async def test_put_zones_returns_404_for_unknown_surface(
    client_with_existdb: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """PUT zones returns 404 when the surface_id does not exist in the document."""
    mock_existdb.get_document.return_value = _TEI_WITH_SURFACE
    token = await _login(client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    res = await client_with_existdb.put(
        _zones_url(assigned_collection.slug, surface_id="no-such-surface"),
        json={"zones": [{"xml_id": "z_f1r_1", "ulx": 0, "uly": 0, "lrx": 10, "lry": 10}]},
        headers=_auth(token),
    )

    assert res.status_code == 404
