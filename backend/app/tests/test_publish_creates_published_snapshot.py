"""Tests for the working/published split (Phase A1 of document versioning).

Verifies that:

1. ``publish_collection`` calls ``existdb.copy_collection_to_published`` with
   the collection slug, populating ``/db/aracne2/published/{slug}``.
2. The publish path stores the working tree fingerprint in
   ``Collection.last_published_tree_hash`` so subsequent publishes can
   short-circuit on unchanged content.
3. ``unpublish_collection`` does **not** delete the published snapshot —
   visibility toggles are PG-only; the eXist-db snapshot survives.
4. A re-publish on identical content skips the copy and the
   ``ON_COLLECTION_PUBLISHED`` hook (the idempotency guard) so deposit
   listeners (Zenodo / Internet Archive / Dataverse / webhooks) do not
   duplicate side effects.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hooks import HookEvent, hook_registry
from app.models.collection import Collection
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    EIC_PASSWORD,
    EIC_USERNAME,
)


@pytest.fixture(autouse=True)
def _clear_publish_hook_handlers() -> Generator[None, None, None]:
    """Strip any plugin handlers registered for the publish/unpublish hooks.

    Other tests in the suite may load deposit plugins (Zenodo, Dataverse,
    Internet Archive) whose ``on_collection_published`` handlers open their
    own ``AsyncSessionLocal`` sessions, bypassing the per-test overrides
    and producing event-loop / connection-pool flakes once they fire from
    a different test's loop. Phase A1 only verifies that the publish path
    invokes ``copy_collection_to_published`` and stores the tree hash —
    plugin reactions are out of scope here, so clear them at setup time.
    """
    snapshot_pub = list(hook_registry._handlers.get(HookEvent.ON_COLLECTION_PUBLISHED, []))
    snapshot_unp = list(hook_registry._handlers.get(HookEvent.ON_COLLECTION_UNPUBLISHED, []))
    hook_registry._handlers[HookEvent.ON_COLLECTION_PUBLISHED] = []
    hook_registry._handlers[HookEvent.ON_COLLECTION_UNPUBLISHED] = []
    try:
        yield
    finally:
        hook_registry._handlers[HookEvent.ON_COLLECTION_PUBLISHED] = snapshot_pub
        hook_registry._handlers[HookEvent.ON_COLLECTION_UNPUBLISHED] = snapshot_unp


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_assign_submit(
    client: AsyncClient, token: str, slug: str
) -> tuple[str, str]:
    """Bring a collection from draft → review and return (id, owner_id)."""
    res = await client.post(
        "/api/v1/collections",
        json={"slug": slug, "title": "Snapshot Test"},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    col_id = res.json()["data"]["id"]
    owner_id = res.json()["data"]["owner_id"]

    res = await client.post(
        f"/api/v1/collections/{col_id}/assign",
        json={"user_id": owner_id, "note": "self-assign for test"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text

    res = await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": "ready"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return col_id, owner_id


@pytest.mark.asyncio
async def test_publish_calls_copy_to_published(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    mock_existdb: object,
    seeded_editorinchief: object,
) -> None:
    """Publishing fires copy_collection_to_published exactly once and stores
    the working tree fingerprint in last_published_tree_hash."""
    client = client_with_existdb
    token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    col_id, _ = await _create_assign_submit(client, token, "snap-1")

    res = await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": "go live"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text

    mock_existdb.copy_collection_to_published.assert_awaited_once_with("snap-1")  # type: ignore[attr-defined]

    db_col = await db_session.scalar(
        select(Collection).where(Collection.slug == "snap-1")
    )
    assert db_col is not None
    assert db_col.last_published_tree_hash is not None
    assert len(db_col.last_published_tree_hash) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_unpublish_preserves_published_snapshot(
    client_with_existdb: AsyncClient,
    mock_existdb: object,
    seeded_admin: object,
    seeded_editorinchief: object,
) -> None:
    """Unpublish toggles visibility (status → draft) without touching the
    eXist-db snapshot — remove_published / delete_collection are not called.

    Unpublish is Admin-only in the current ACL; the publish path is EiC.
    """
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    col_id, _ = await _create_assign_submit(client, eic_token, "snap-2")

    res = await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": "go live"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text

    mock_existdb.copy_collection_to_published.assert_awaited_once_with("snap-2")  # type: ignore[attr-defined]
    mock_existdb.copy_collection_to_published.reset_mock()  # type: ignore[attr-defined]

    res = await client.post(
        f"/api/v1/collections/{col_id}/unpublish",
        json={"note": "rollback to draft"},
        headers=_auth(admin_token),
    )
    assert res.status_code == 200, res.text

    mock_existdb.copy_collection_to_published.assert_not_awaited()  # type: ignore[attr-defined]
    mock_existdb.remove_published.assert_not_awaited()  # type: ignore[attr-defined]
    mock_existdb.delete_collection.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_republish_unchanged_content_skips_copy(
    client_with_existdb: AsyncClient,
    mock_existdb: object,
    seeded_admin: object,
    seeded_editorinchief: object,
) -> None:
    """A second publish on identical working-tree content does not re-invoke
    copy_collection_to_published — last_published_tree_hash matches and the
    publish is treated as a no-op for downstream listeners."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    col_id, owner_id = await _create_assign_submit(client, eic_token, "snap-3")

    # First publish — copy must fire.
    res = await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": "first publish"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text
    assert mock_existdb.copy_collection_to_published.await_count == 1  # type: ignore[attr-defined]

    # Unpublish (Admin) → status=draft. Re-walk to review with the EiC.
    res = await client.post(
        f"/api/v1/collections/{col_id}/unpublish",
        json={"note": "back to draft"},
        headers=_auth(admin_token),
    )
    assert res.status_code == 200, res.text

    res = await client.post(
        f"/api/v1/collections/{col_id}/assign",
        json={"user_id": owner_id, "note": "re-assign"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text
    res = await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": "ready again"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text

    # Second publish on unchanged tree — copy must NOT fire again.
    res = await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": "republish unchanged"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text
    assert mock_existdb.copy_collection_to_published.await_count == 1  # type: ignore[attr-defined]
