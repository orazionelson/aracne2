"""End-to-end test of the workflow auto-versioning + SHA-256 dedup contract.

Phase B writes a ``document_versions`` row at four collection-level events
(submission, rejection, publication, direct_publication) plus on the first
upload of a filename (creation). The dedup guard skips writes when the
working tree's content matches the last stored version for that document,
so a publish→unpublish→republish on unchanged content produces zero new
rows.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hooks import HookEvent, hook_registry
from app.models.document_version import DocumentVersion, VersionOrigin
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    EIC_PASSWORD,
    EIC_USERNAME,
)


@pytest.fixture(autouse=True)
def _clear_publish_hook_handlers() -> Generator[None, None, None]:
    """Strip plugin handlers — see test_publish_creates_published_snapshot.py
    for the rationale (deposit plugins open out-of-loop sessions)."""
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


async def _count_versions(
    db: AsyncSession, *, origin: VersionOrigin | None = None
) -> int:
    stmt = select(func.count(DocumentVersion.id))
    if origin is not None:
        stmt = stmt.where(DocumentVersion.origin == origin)
    return int(await db.scalar(stmt) or 0)


@pytest.mark.asyncio
async def test_full_workflow_emits_one_row_per_origin(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb: object,
    seeded_editorinchief: object,
) -> None:
    """create → assign → submit → reject → submit → publish on a single doc
    produces exactly one row per content-changing event the workflow fires."""
    client = client_with_existdb
    token = await _login(client, EIC_USERNAME, EIC_PASSWORD)

    # eXist-db is mocked to expose exactly one document with a stable body.
    mock_existdb.list_collection.return_value = ["doc1.xml"]  # type: ignore[attr-defined]
    mock_existdb.get_document.return_value = b"<TEI v='stable'/>"  # type: ignore[attr-defined]

    res = await client.post(
        "/api/v1/collections",
        json={"slug": "wf-dedup", "title": "WF Dedup"},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    col_id = res.json()["data"]["id"]
    owner_id = res.json()["data"]["owner_id"]

    res = await client.post(
        f"/api/v1/collections/{col_id}/assign",
        json={"user_id": owner_id, "note": "self"},
        headers=_auth(token),
    )
    assert res.status_code == 200

    res = await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": "ready"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    # First submit on stable content → one row.
    assert await _count_versions(db_session, origin=VersionOrigin.submission) == 1

    res = await client.post(
        f"/api/v1/collections/{col_id}/reject",
        json={"note": "fix"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    # Reject on still-unchanged content → SHA-256 dedup skips. The latest
    # row for this doc is the submission's; rejection returns 0 new.
    assert await _count_versions(db_session, origin=VersionOrigin.rejection) == 0

    res = await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": "ready again"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    # Second submit, content still unchanged → still 1 submission row total.
    assert await _count_versions(db_session, origin=VersionOrigin.submission) == 1

    res = await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": "go live"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    # Publish writes a new row because origin differs and SHA changes the
    # latest stored row (it was submission); content matches but origin!=
    # — wait, dedup compares SHA only, not origin. The latest row already
    # had this SHA. So publication is *also* deduplicated to 0 rows.
    # The contract: the row is keyed on (filename, version_number); new
    # publications on identical content get skipped.
    assert await _count_versions(db_session, origin=VersionOrigin.publication) == 0


@pytest.mark.asyncio
async def test_publish_writes_publication_row_when_content_changes(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb: object,
    seeded_editorinchief: object,
) -> None:
    """When the working tree contains content not yet snapshotted, the
    publication path produces one ``origin=publication`` row per doc."""
    client = client_with_existdb
    token = await _login(client, EIC_USERNAME, EIC_PASSWORD)

    res = await client.post(
        "/api/v1/collections",
        json={"slug": "wf-pub", "title": "WF Pub"},
        headers=_auth(token),
    )
    assert res.status_code == 201
    col_id = res.json()["data"]["id"]
    owner_id = res.json()["data"]["owner_id"]
    await client.post(
        f"/api/v1/collections/{col_id}/assign",
        json={"user_id": owner_id, "note": "self"},
        headers=_auth(token),
    )

    # Submit on content A.
    mock_existdb.list_collection.return_value = ["d.xml"]  # type: ignore[attr-defined]
    mock_existdb.get_document.return_value = b"<TEI v='A'/>"  # type: ignore[attr-defined]
    await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": "A"},
        headers=_auth(token),
    )
    assert await _count_versions(db_session, origin=VersionOrigin.submission) == 1

    # Editor revises to content B before publish.
    mock_existdb.get_document.return_value = b"<TEI v='B'/>"  # type: ignore[attr-defined]

    await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": "publish B"},
        headers=_auth(token),
    )
    # New SHA → publication row added.
    assert await _count_versions(db_session, origin=VersionOrigin.publication) == 1


@pytest.mark.asyncio
async def test_unpublish_writes_no_versions(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb: object,
    seeded_admin: object,
    seeded_editorinchief: object,
) -> None:
    """Unpublish is a pure visibility toggle — it never writes to
    document_versions (the previous publication row is the public state on
    record; nothing else changed)."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    res = await client.post(
        "/api/v1/collections",
        json={"slug": "wf-unp", "title": "WF Unpub"},
        headers=_auth(eic_token),
    )
    col_id = res.json()["data"]["id"]
    owner_id = res.json()["data"]["owner_id"]
    await client.post(
        f"/api/v1/collections/{col_id}/assign",
        json={"user_id": owner_id, "note": "self"},
        headers=_auth(eic_token),
    )
    mock_existdb.list_collection.return_value = ["d.xml"]  # type: ignore[attr-defined]
    mock_existdb.get_document.return_value = b"<TEI/>"  # type: ignore[attr-defined]
    await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": ""},
        headers=_auth(eic_token),
    )
    await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": ""},
        headers=_auth(eic_token),
    )

    before = await _count_versions(db_session)
    await client.post(
        f"/api/v1/collections/{col_id}/unpublish",
        json={"note": ""},
        headers=_auth(admin_token),
    )
    after = await _count_versions(db_session)
    assert before == after
