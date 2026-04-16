"""Tests for the Named Entity Index plugin endpoints (/entities/*).

Public endpoints require no authentication.
Admin-panel endpoints require Admin or EditorInChief roles.
The reindex endpoint is mocked at the service layer to avoid opening
AsyncSessionLocal connections to real Postgres inside the test process.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.plugins._native.named_entities.models import EntityOccurrence, NamedEntity
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
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
async def published_collection(db_session: AsyncSession) -> Collection:
    col = Collection(
        slug="entities-test-col",
        title="Entities Test Collection",
        status=CollectionStatus.published,
        is_public=True,
    )
    db_session.add(col)
    await db_session.flush()
    return col


@pytest_asyncio.fixture
async def seeded_entity(
    db_session: AsyncSession, published_collection: Collection
) -> NamedEntity:
    """A named entity with one occurrence in the published collection."""
    entity = NamedEntity(
        type="persName",
        canonical_form="John Doe",
        occurrence_count=1,
    )
    db_session.add(entity)
    await db_session.flush()
    occ = EntityOccurrence(
        entity_id=entity.id,
        collection_id=published_collection.id,
        filename="doc.xml",
        raw_form="John Doe",
    )
    db_session.add(occ)
    await db_session.flush()
    return entity


# ── Public endpoints ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_entities_public_returns_empty(client: AsyncClient) -> None:
    """GET /entities is public and returns an empty list when no entities exist."""
    res = await client.get("/api/v1/entities")
    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_list_entities_returns_seeded_entity(
    client: AsyncClient,
    seeded_entity: NamedEntity,
    published_collection: Collection,
) -> None:
    """GET /entities returns entities indexed in published public collections."""
    res = await client.get("/api/v1/entities")
    assert res.status_code == 200
    canonical_forms = [e["canonical_form"] for e in res.json()["data"]]
    assert "John Doe" in canonical_forms


@pytest.mark.asyncio
async def test_list_entity_occurrences(
    client: AsyncClient,
    seeded_entity: NamedEntity,
    published_collection: Collection,
) -> None:
    """GET /entities/{id}/occurrences returns occurrences for the entity."""
    res = await client.get(f"/api/v1/entities/{seeded_entity.id}/occurrences")
    assert res.status_code == 200
    assert res.json()["data"][0]["filename"] == "doc.xml"


# ── Admin endpoints ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_entities_as_admin(
    client: AsyncClient,
    seeded_admin: User,
    seeded_entity: NamedEntity,
) -> None:
    """Admin can list all named entities."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/entities/admin", headers=_auth(token))
    assert res.status_code == 200
    canonical_forms = [e["canonical_form"] for e in res.json()["data"]]
    assert "John Doe" in canonical_forms


@pytest.mark.asyncio
async def test_admin_list_entities_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Non-Admin cannot access the admin entity list."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/entities/admin", headers=_auth(token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_get_tag_config_as_eic(
    client: AsyncClient, seeded_editorinchief: User
) -> None:
    """EiC+ can retrieve the current tag configuration."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.get("/api/v1/entities/admin/tag-config", headers=_auth(token))
    assert res.status_code == 200
    assert isinstance(res.json()["data"], list)


@pytest.mark.asyncio
async def test_admin_get_tag_config_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor cannot access the tag configuration."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/entities/admin/tag-config", headers=_auth(token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_put_tag_config_as_eic(
    client: AsyncClient, seeded_editorinchief: User
) -> None:
    """EiC+ can update the tag configuration."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.put(
        "/api/v1/entities/admin/tag-config",
        headers=_auth(token),
        json={"tags": ["persName", "placeName", "orgName"]},
    )
    assert res.status_code == 200
    assert res.json()["data"] == ["persName", "placeName", "orgName"]


@pytest.mark.asyncio
async def test_admin_update_entity_not_found_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Updating a non-existent entity returns 404."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.put(
        f"/api/v1/entities/admin/{uuid.uuid4()}",
        headers=_auth(token),
        json={"canonical_form": "New Name"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_entity_not_found_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Deleting a non-existent entity returns 404."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/entities/admin/{uuid.uuid4()}", headers=_auth(token)
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_entity_as_admin(
    client: AsyncClient,
    seeded_admin: User,
    seeded_entity: NamedEntity,
) -> None:
    """Admin can delete an existing named entity."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/entities/admin/{seeded_entity.id}", headers=_auth(token)
    )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_admin_merge_entities_not_found_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Merging non-existent entities returns 404."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/entities/admin/merge",
        headers=_auth(token),
        json={"source_id": str(uuid.uuid4()), "target_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_admin_reindex_collection_not_found_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Reindexing a non-existent collection returns 404."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/entities/admin/reindex/nonexistent-col",
        headers=_auth(token),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_admin_reindex_collection_happy_path(
    client: AsyncClient,
    seeded_admin: User,
    published_collection: Collection,
) -> None:
    """Admin can trigger a full re-index of an existing collection."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    with patch(
        "app.plugins._native.named_entities.service.reindex_collection",
        new=AsyncMock(return_value=42),
    ):
        res = await client.post(
            f"/api/v1/entities/admin/reindex/{published_collection.slug}",
            headers=_auth(token),
        )
    assert res.status_code == 200
    assert res.json()["data"]["occurrences_indexed"] == 42
