"""Tests for the collection bibliography endpoints.

All bibliography endpoints require EditorInChief+ (EiC+).
The public-bibliography endpoint is unauthenticated but requires
the collection to be published and is_public=True.

No eXist-db calls are made by these endpoints — they are Postgres-only.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.tests.conftest import (
    EIC_PASSWORD,
    EIC_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def eic_collection(
    db_session: AsyncSession, seeded_editorinchief: User
) -> Collection:
    """A published public collection owned by the EditorInChief."""
    col = Collection(
        slug="bibl-test-col",
        title="Bibliography Test Collection",
        status=CollectionStatus.published,
        is_public=True,
        owner_id=seeded_editorinchief.id,
    )
    db_session.add(col)
    await db_session.flush()
    return col


# ── Save bibliography ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_bibliography_as_eic_returns_201(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """EditorInChief can save a new bibliography version (auto-versioned)."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.post(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
        json={"content": "<bibl>Author A (2020)</bibl>"},
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["version"] == 1
    assert data["content"] == "<bibl>Author A (2020)</bibl>"
    assert data["is_public"] is False


@pytest.mark.asyncio
async def test_save_bibliography_auto_increments_version(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """Saving a second bibliography version assigns version 2 automatically."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    for content in ["v1 content", "v2 content"]:
        res = await client.post(
            f"/api/v1/collections/{eic_collection.slug}/bibliographies",
            headers=_auth(token),
            json={"content": content},
        )
        assert res.status_code == 201
    assert res.json()["data"]["version"] == 2


@pytest.mark.asyncio
async def test_save_bibliography_as_editor_returns_403(
    client: AsyncClient,
    seeded_user: User,
    eic_collection: Collection,
) -> None:
    """Editor (level 2) cannot save a bibliography — requires EiC+."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
        json={"content": "ignored"},
    )
    assert res.status_code == 403


# ── List bibliographies ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_bibliographies_empty_for_new_collection(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """A new collection has no saved bibliography versions."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.get(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_list_bibliographies_newest_first(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """Saved bibliography versions are returned newest-first."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    for content in ["v1", "v2", "v3"]:
        await client.post(
            f"/api/v1/collections/{eic_collection.slug}/bibliographies",
            headers=_auth(token),
            json={"content": content},
        )
    res = await client.get(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
    )
    assert res.status_code == 200
    versions = [b["version"] for b in res.json()["data"]]
    assert versions == [3, 2, 1]


# ── Delete bibliography ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_bibliography_version(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """EiC can delete a specific bibliography version."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    await client.post(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
        json={"content": "to be deleted"},
    )
    res = await client.delete(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies/1",
        headers=_auth(token),
    )
    assert res.status_code == 204
    # Confirm it's gone
    list_res = await client.get(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
    )
    assert list_res.json()["data"] == []


@pytest.mark.asyncio
async def test_delete_nonexistent_bibliography_version_returns_404(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """Deleting a version that doesn't exist returns 404."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.delete(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies/99",
        headers=_auth(token),
    )
    assert res.status_code == 404


# ── Set public flag ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_bibliography_public_flag(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """Marking a bibliography version as public is_public=True."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    await client.post(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
        json={"content": "public content"},
    )
    res = await client.patch(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies/1",
        headers=_auth(token),
        json={"is_public": True},
    )
    assert res.status_code == 200
    assert res.json()["data"]["is_public"] is True


@pytest.mark.asyncio
async def test_set_public_flag_clears_other_versions(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """Making version 2 public automatically un-publishes version 1."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    for content in ["v1", "v2"]:
        await client.post(
            f"/api/v1/collections/{eic_collection.slug}/bibliographies",
            headers=_auth(token),
            json={"content": content},
        )
    # Publish version 1 first
    await client.patch(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies/1",
        headers=_auth(token),
        json={"is_public": True},
    )
    # Now publish version 2 — version 1 must become private
    await client.patch(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies/2",
        headers=_auth(token),
        json={"is_public": True},
    )
    all_res = await client.get(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
    )
    by_version = {b["version"]: b["is_public"] for b in all_res.json()["data"]}
    assert by_version[2] is True
    assert by_version[1] is False


# ── Public bibliography ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_bibliography_returns_published_version(
    client: AsyncClient,
    seeded_editorinchief: User,
    eic_collection: Collection,
) -> None:
    """GET /public-bibliography returns the public version without authentication."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    await client.post(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies",
        headers=_auth(token),
        json={"content": "public bibliography content"},
    )
    await client.patch(
        f"/api/v1/collections/{eic_collection.slug}/bibliographies/1",
        headers=_auth(token),
        json={"is_public": True},
    )
    # Unauthenticated request
    res = await client.get(
        f"/api/v1/collections/{eic_collection.slug}/public-bibliography"
    )
    assert res.status_code == 200
    assert res.json()["data"]["content"] == "public bibliography content"


@pytest.mark.asyncio
async def test_public_bibliography_returns_404_when_none_public(
    client: AsyncClient,
    eic_collection: Collection,
) -> None:
    """GET /public-bibliography returns 404 when no version is marked public."""
    res = await client.get(
        f"/api/v1/collections/{eic_collection.slug}/public-bibliography"
    )
    assert res.status_code == 404
