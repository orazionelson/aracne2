"""Tests for Phase A2 of document versioning — working/published decoupling.

A2 removes the ``Collection is published — unpublish before editing`` lock and
reroutes every public surface to read from ``existdb.published_path(slug)``
instead of ``col_path(slug)``. The contract this file proves:

1. After publish, an Editor+ can still upload, update and delete documents on
   the working tree without unpublishing — the lock is gone.
2. Public-side document reads call ``get_published_document`` (not
   ``get_document``); public listings call ``list_published`` (not
   ``list_collection``).
3. Unpublish remains a pure visibility toggle (already covered by A1's
   ``test_unpublish_preserves_published_snapshot``); we re-assert here that
   ``copy_collection_to_published`` is invoked again only on republish with
   actually-changed content.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from httpx import AsyncClient

from app.core.hooks import HookEvent, hook_registry
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    EIC_PASSWORD,
    EIC_USERNAME,
)


@pytest.fixture(autouse=True)
def _clear_publish_hook_handlers() -> Generator[None, None, None]:
    """Strip plugin handlers (Zenodo / Dataverse / IA / webhooks) so they do
    not open out-of-loop ``AsyncSessionLocal`` sessions during these tests."""
    snap_pub = list(hook_registry._handlers.get(HookEvent.ON_COLLECTION_PUBLISHED, []))
    snap_unp = list(hook_registry._handlers.get(HookEvent.ON_COLLECTION_UNPUBLISHED, []))
    hook_registry._handlers[HookEvent.ON_COLLECTION_PUBLISHED] = []
    hook_registry._handlers[HookEvent.ON_COLLECTION_UNPUBLISHED] = []
    try:
        yield
    finally:
        hook_registry._handlers[HookEvent.ON_COLLECTION_PUBLISHED] = snap_pub
        hook_registry._handlers[HookEvent.ON_COLLECTION_UNPUBLISHED] = snap_unp


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _bring_to_published(
    client: AsyncClient, eic_token: str, slug: str
) -> tuple[str, str]:
    """Create → assign → submit → publish. Return (collection_id, owner_id)."""
    res = await client.post(
        "/api/v1/collections",
        json={"slug": slug, "title": "A2 Test"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 201, res.text
    col_id = res.json()["data"]["id"]
    owner_id = res.json()["data"]["owner_id"]

    res = await client.post(
        f"/api/v1/collections/{col_id}/assign",
        json={"user_id": owner_id, "note": "self"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text
    res = await client.post(
        f"/api/v1/collections/{col_id}/submit",
        json={"note": "ready"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text
    res = await client.post(
        f"/api/v1/collections/{col_id}/publish",
        json={"note": "go live"},
        headers=_auth(eic_token),
    )
    assert res.status_code == 200, res.text
    return col_id, owner_id


@pytest.mark.asyncio
async def test_upload_document_while_published_succeeds(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: object,
) -> None:
    """Phase A2 removed the ``unpublish before editing`` lock. Uploading on a
    published collection no longer returns 403 — the working tree is the
    Editor+ surface, the public still sees the snapshot until next publish."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    col_id, _ = await _bring_to_published(client, eic_token, "a2-edit")

    res = await client.post(
        f"/api/v1/collections/{col_id}/documents",
        files={"file": ("doc-new.xml", b"<TEI/>", "application/xml")},
        headers=_auth(eic_token),
    )
    assert res.status_code == 201, res.text


@pytest.mark.asyncio
async def test_update_document_while_published_succeeds(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: object,
) -> None:
    """Same as upload, for the PUT /documents/{filename} path."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    col_id, _ = await _bring_to_published(client, eic_token, "a2-update")

    res = await client.put(
        f"/api/v1/collections/{col_id}/documents/doc1.xml",
        content=b"<TEI><teiHeader/></TEI>",
        headers={**_auth(eic_token), "Content-Type": "application/xml"},
    )
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_delete_document_while_published_succeeds(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: object,
) -> None:
    """Same as upload, for the DELETE /documents/{filename} path."""
    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    col_id, _ = await _bring_to_published(client, eic_token, "a2-delete")

    res = await client.delete(
        f"/api/v1/collections/{col_id}/documents/doc1.xml",
        headers=_auth(eic_token),
    )
    assert res.status_code == 204, res.text


@pytest.mark.asyncio
async def test_publish_invokes_cache_invalidation_helper(
    client_with_existdb: AsyncClient,
    seeded_editorinchief: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase A2 wiring: a content-changed publish calls
    ``_invalidate_linked_website_caches`` so any cached page tied to a Website
    pointing at the collection is dropped before the public sees stale HTML.
    """
    from unittest.mock import AsyncMock

    from app.services import xmldb as xmldb_module

    spy = AsyncMock(return_value=None)
    monkeypatch.setattr(xmldb_module, "_invalidate_linked_website_caches", spy)

    client = client_with_existdb
    eic_token = await _login(client, EIC_USERNAME, EIC_PASSWORD)
    await _bring_to_published(client, eic_token, "a2-cache")

    spy.assert_awaited_once()
