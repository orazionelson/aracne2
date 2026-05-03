"""HTTP-level tests for the editor REST surface added in Phase C.

Covers the six endpoints under
``/api/v1/collections/{id}/documents/{filename}/versions[...]``:

- list (with ``?origin=`` filter)
- get version metadata
- get version raw XML body
- manual save (``POST .../versions``)
- rollback (``POST .../versions/{n}/rollback``)
- diff (``GET .../versions/{n}/diff?against=M``)
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hooks import HookEvent, hook_registry
from app.models.collection import Collection, CollectionStatus
from app.models.document_version import DocumentVersion, VersionOrigin
from app.tests.conftest import (
    EIC_PASSWORD,
    EIC_USERNAME,
)


@pytest.fixture(autouse=True)
def _clear_publish_hook_handlers() -> Generator[None, None, None]:
    snap_pub = list(hook_registry._handlers.get(HookEvent.ON_COLLECTION_PUBLISHED, []))
    snap_unp = list(hook_registry._handlers.get(HookEvent.ON_COLLECTION_UNPUBLISHED, []))
    snap_sub = list(hook_registry._handlers.get(HookEvent.ON_COLLECTION_SUBMITTED, []))
    hook_registry._handlers[HookEvent.ON_COLLECTION_PUBLISHED] = []
    hook_registry._handlers[HookEvent.ON_COLLECTION_UNPUBLISHED] = []
    hook_registry._handlers[HookEvent.ON_COLLECTION_SUBMITTED] = []
    try:
        yield
    finally:
        hook_registry._handlers[HookEvent.ON_COLLECTION_PUBLISHED] = snap_pub
        hook_registry._handlers[HookEvent.ON_COLLECTION_UNPUBLISHED] = snap_unp
        hook_registry._handlers[HookEvent.ON_COLLECTION_SUBMITTED] = snap_sub


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def public_collection(db_session: AsyncSession) -> Collection:
    """A published, public collection — needed for the public ``?version=N``
    endpoint which gates on ``status == published AND is_public``."""
    col = Collection(
        slug="ep-public",
        title="Versioning Endpoints Public",
        status=CollectionStatus.published,
        is_public=True,
    )
    db_session.add(col)
    await db_session.flush()
    return col


async def _make_assigned_collection(
    db: AsyncSession,
    eic_user_id,
    slug: str,
) -> Collection:
    """Create a collection in 'assigned' state owned by the EiC.

    Going through HTTP would require seeding the EiC and walking
    create→assign which is heavier than the data-layer setup needed for
    these endpoint tests."""
    col = Collection(
        slug=slug,
        title="Endpoints Test",
        status=CollectionStatus.assigned,
        editor_id=eic_user_id,
        owner_id=eic_user_id,
    )
    db.add(col)
    await db.flush()
    return col


@pytest.mark.asyncio
async def test_list_versions_empty_when_no_history(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief,
) -> None:
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-empty"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)

    res = await client_with_existdb.get(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions",
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_manual_save_creates_version_via_http(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb,
    seeded_editorinchief,
) -> None:
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-manual"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)
    mock_existdb.get_document.return_value = b"<TEI/>"

    res = await client_with_existdb.post(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions",
        json={"message": "wip checkpoint"},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["origin"] == "manual"
    assert body["message"] == "wip checkpoint"
    assert body["version_number"] == 1


@pytest.mark.asyncio
async def test_get_version_content_returns_raw_xml(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb,
    seeded_editorinchief,
) -> None:
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-content"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)
    body_bytes = b"<TEI><teiHeader/></TEI>"
    mock_existdb.get_document.return_value = body_bytes

    # First create a row through the manual save endpoint.
    res = await client_with_existdb.post(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions",
        json={"message": "first"},
        headers=_auth(token),
    )
    assert res.status_code == 201
    n = res.json()["data"]["version_number"]

    res = await client_with_existdb.get(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions/{n}/content",
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/xml")
    assert res.content == body_bytes


@pytest.mark.asyncio
async def test_list_origin_filter(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb,
    seeded_editorinchief,
) -> None:
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-filter"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)

    # Seed two manual rows directly.
    from app.services.document_versions import create_version

    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='1'/>",
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='2'/>",
        origin=VersionOrigin.publication,
        actor=seeded_editorinchief,
    )
    await db_session.flush()

    res = await client_with_existdb.get(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions?origin=publication",
        headers=_auth(token),
    )
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 1
    assert rows[0]["origin"] == "publication"


@pytest.mark.asyncio
async def test_rollback_endpoint_writes_row_and_pushes_to_existdb(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb,
    seeded_editorinchief,
) -> None:
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-rollback"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)

    # Seed a target version.
    from app.services.document_versions import create_version

    target = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI v='target'/>",
        origin=VersionOrigin.manual,
        actor=seeded_editorinchief,
        skip_dedup=True,
    )
    await db_session.flush()
    assert target is not None
    mock_existdb.put_document.reset_mock()

    res = await client_with_existdb.post(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions/"
        f"{target.version_number}/rollback",
        json={"note": "back to target"},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["data"]["origin"] == "rollback"

    # eXist-db received the target body on the working tree path.
    mock_existdb.put_document.assert_awaited_once()
    args, _ = mock_existdb.put_document.call_args
    assert args[0] == "ep-rollback"
    assert args[1] == "d.xml"
    assert args[2] == b"<TEI v='target'/>"


@pytest.mark.asyncio
async def test_diff_endpoint_returns_unified_diff(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief,
) -> None:
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-diff"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)

    from app.services.document_versions import create_version

    a = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI>\n  <teiHeader/>\n  <text>A</text>\n</TEI>\n",
        origin=VersionOrigin.creation,
        actor=seeded_editorinchief,
    )
    b = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI>\n  <teiHeader/>\n  <text>B</text>\n</TEI>\n",
        origin=VersionOrigin.publication,
        actor=seeded_editorinchief,
    )
    await db_session.flush()
    assert a is not None and b is not None

    res = await client_with_existdb.get(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions/"
        f"{b.version_number}/diff?against={a.version_number}",
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    payload = res.json()["data"]
    assert payload["from_version"] == a.version_number
    assert payload["to_version"] == b.version_number
    assert "<text>A</text>" in payload["diff"]
    assert "<text>B</text>" in payload["diff"]
    assert payload["diff"].startswith("---")


@pytest.mark.asyncio
async def test_get_unknown_version_returns_404(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief,
) -> None:
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-404"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)

    res = await client_with_existdb.get(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions/42",
        headers=_auth(token),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_own_manual_version_succeeds(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb,
    seeded_editorinchief,
) -> None:
    """An editor can delete their own manual save row to make room against
    the soft cap."""
    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-del-own"
    )
    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)
    mock_existdb.get_document.return_value = b"<TEI/>"

    res = await client_with_existdb.post(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions",
        json={"message": "checkpoint"},
        headers=_auth(token),
    )
    n = res.json()["data"]["version_number"]

    res = await client_with_existdb.delete(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions/{n}",
        headers=_auth(token),
    )
    assert res.status_code == 204, res.text

    # Listing now returns no rows.
    res = await client_with_existdb.get(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions",
        headers=_auth(token),
    )
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_delete_other_authors_manual_version_forbidden(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_user,
    seeded_editorinchief,
) -> None:
    """A non-Admin caller who is not the author of a manual row cannot
    delete it. Per-row authorisation is the gate, independent of whether
    the user has write access to the collection."""
    from app.services.document_versions import create_version
    from app.tests.conftest import TEST_USER_PASSWORD, TEST_USER_USERNAME

    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-del-other"
    )
    # Manual save authored by the EiC.
    row = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI/>",
        origin=VersionOrigin.manual,
        actor=seeded_editorinchief,
        skip_dedup=True,
    )
    await db_session.flush()
    assert row is not None

    user_token = await _login(
        client_with_existdb, TEST_USER_USERNAME, TEST_USER_PASSWORD
    )
    res = await client_with_existdb.delete(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions/"
        f"{row.version_number}",
        headers=_auth(user_token),
    )
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_delete_auto_version_returns_422(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_editorinchief,
) -> None:
    """Auto rows (creation / submission / rejection / publication / rollback)
    are append-only — the editorial integrity record cannot be erased."""
    from app.services.document_versions import create_version

    col = await _make_assigned_collection(
        db_session, seeded_editorinchief.id, "ep-del-auto"
    )
    row = await create_version(
        db_session,
        collection=col,
        filename="d.xml",
        xml_bytes=b"<TEI/>",
        origin=VersionOrigin.publication,
        actor=seeded_editorinchief,
    )
    await db_session.flush()
    assert row is not None

    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)
    res = await client_with_existdb.delete(
        f"/api/v1/collections/{col.id}/documents/d.xml/versions/"
        f"{row.version_number}",
        headers=_auth(token),
    )
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "VERSION_NOT_DELETABLE"


@pytest.mark.asyncio
async def test_public_permalink_returns_publication_with_noindex(
    client: AsyncClient,
    db_session: AsyncSession,
    public_collection: Collection,
    seeded_editorinchief,
) -> None:
    """``?version=N`` on the public render endpoint serves the historic
    publication body with X-Robots-Tag: noindex and a canonical link back
    to the live URL. Manual / rollback / creation versions are 404."""
    from app.services.document_versions import create_version

    minimal_tei = (
        b"<?xml version='1.0'?>"
        b"<TEI xmlns='http://www.tei-c.org/ns/1.0'>"
        b"<teiHeader><fileDesc>"
        b"<titleStmt><title>T</title></titleStmt>"
        b"<publicationStmt><p>P</p></publicationStmt>"
        b"<sourceDesc><p>S</p></sourceDesc>"
        b"</fileDesc></teiHeader>"
        b"<text><body><p>HISTORIC</p></body></text>"
        b"</TEI>"
    )

    pub_row = await create_version(
        db_session,
        collection=public_collection,
        filename="hist.xml",
        xml_bytes=minimal_tei,
        origin=VersionOrigin.publication,
        actor=seeded_editorinchief,
    )
    manual_row = await create_version(
        db_session,
        collection=public_collection,
        filename="hist.xml",
        xml_bytes=b"<TEI><manual/></TEI>",
        origin=VersionOrigin.manual,
        actor=seeded_editorinchief,
        skip_dedup=True,
    )
    await db_session.flush()
    assert pub_row is not None and manual_row is not None

    # Hit the publication version → 200 + noindex header + canonical link.
    res = await client.get(
        f"/api/v1/public/collections/{public_collection.slug}"
        f"/documents/hist.xml?version={pub_row.version_number}"
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("x-robots-tag") == "noindex"
    assert 'rel="canonical"' in res.text
    assert "HISTORIC" in res.text

    # Manual row → 404 (VersionNotPublic).
    res = await client.get(
        f"/api/v1/public/collections/{public_collection.slug}"
        f"/documents/hist.xml?version={manual_row.version_number}"
    )
    assert res.status_code == 404
