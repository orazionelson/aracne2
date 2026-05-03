"""Tests for the ``has_unpublished_changes`` flag (Phase E).

Covers the four cases the helper has to distinguish:

- never published, empty working tree → False (nothing to publish)
- never published, non-empty working tree → True (the editor has uploaded
  documents that have never reached the public)
- published, working tree fingerprint matches last_published_tree_hash
  → False (re-publish would be a no-op)
- published, working tree fingerprint differs → True (re-publish would
  propagate real changes)

Plus the HTTP-level smoke check that the detail endpoint surfaces the
field on its response payload.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hooks import HookEvent, hook_registry
from app.db.existdb import ExistDBClient
from app.models.collection import Collection, CollectionStatus
from app.services.xmldb import compute_has_unpublished_changes
from app.tests.conftest import EIC_PASSWORD, EIC_USERNAME


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


def _mock_existdb(filenames: list[str], body_for: dict[str, bytes] | None = None) -> ExistDBClient:
    mock = AsyncMock(spec=ExistDBClient)
    mock.list_collection = AsyncMock(return_value=filenames)
    if body_for is None:
        mock.get_document = AsyncMock(return_value=b"<TEI/>")
    else:
        mock.get_document = AsyncMock(side_effect=lambda slug, name: body_for[name])
    return mock


@pytest.mark.asyncio
async def test_never_published_empty_returns_false(
    db_session: AsyncSession,
) -> None:
    col = Collection(
        slug="hu-empty", title="X", status=CollectionStatus.draft
    )
    db_session.add(col)
    await db_session.flush()

    flag = await compute_has_unpublished_changes(_mock_existdb([]), col)
    assert flag is False


@pytest.mark.asyncio
async def test_never_published_with_docs_returns_true(
    db_session: AsyncSession,
) -> None:
    col = Collection(
        slug="hu-draft", title="X", status=CollectionStatus.draft
    )
    db_session.add(col)
    await db_session.flush()

    flag = await compute_has_unpublished_changes(
        _mock_existdb(["d.xml"], {"d.xml": b"<TEI/>"}), col
    )
    assert flag is True


@pytest.mark.asyncio
async def test_published_matching_hash_returns_false(
    db_session: AsyncSession,
) -> None:
    """The hash stored in last_published_tree_hash matches the current
    working-tree fingerprint computed by _compute_collection_tree_hash."""
    import hashlib

    body = b"<TEI/>"
    digest = hashlib.sha256(body).hexdigest()
    tree_hash = hashlib.sha256(f"d.xml\0{digest}\n".encode()).hexdigest()

    col = Collection(
        slug="hu-pub-match",
        title="X",
        status=CollectionStatus.published,
        last_published_tree_hash=tree_hash,
    )
    db_session.add(col)
    await db_session.flush()

    flag = await compute_has_unpublished_changes(
        _mock_existdb(["d.xml"], {"d.xml": body}), col
    )
    assert flag is False


@pytest.mark.asyncio
async def test_published_diverged_hash_returns_true(
    db_session: AsyncSession,
) -> None:
    col = Collection(
        slug="hu-pub-drift",
        title="X",
        status=CollectionStatus.published,
        last_published_tree_hash="0" * 64,
    )
    db_session.add(col)
    await db_session.flush()

    flag = await compute_has_unpublished_changes(
        _mock_existdb(["d.xml"], {"d.xml": b"<TEI/>"}), col
    )
    assert flag is True


@pytest.mark.asyncio
async def test_existdb_failure_returns_false_safely(
    db_session: AsyncSession,
) -> None:
    """eXist-db transient failure must not crash the badge computation —
    the detail endpoint stays responsive, the badge just stays absent."""
    col = Collection(
        slug="hu-fail",
        title="X",
        status=CollectionStatus.published,
        last_published_tree_hash="abc",
    )
    db_session.add(col)
    await db_session.flush()

    mock = AsyncMock(spec=ExistDBClient)
    mock.list_collection = AsyncMock(side_effect=RuntimeError("boom"))
    mock.get_document = AsyncMock(side_effect=RuntimeError("boom"))

    flag = await compute_has_unpublished_changes(mock, col)
    assert flag is False


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_collection_detail_surfaces_has_unpublished_changes(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb,
    seeded_editorinchief: object,
) -> None:
    """``GET /collections/{id}`` includes ``has_unpublished_changes`` in
    its response payload — the field is what the frontend badge checks."""
    col = Collection(
        slug="hu-http",
        title="X",
        status=CollectionStatus.draft,
        editor_id=seeded_editorinchief.id,
        owner_id=seeded_editorinchief.id,
    )
    db_session.add(col)
    await db_session.flush()

    mock_existdb.list_collection.return_value = ["d.xml"]
    mock_existdb.get_document.return_value = b"<TEI/>"

    token = await _login(client_with_existdb, EIC_USERNAME, EIC_PASSWORD)
    res = await client_with_existdb.get(
        f"/api/v1/collections/{col.id}", headers=_auth(token)
    )
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    # Draft + non-empty working tree → True (every doc is unpublished work).
    assert body["has_unpublished_changes"] is True
