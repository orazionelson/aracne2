"""Tests for the TEI schema management endpoints (/schemas/*).

File-based operations (upload, generate, get-cm5) patch settings.schemas_dir
to a tmp_path so no real filesystem state is touched during tests.
"""

import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tei_schema import TeiSchema
from app.models.user import User
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
async def seeded_schema(db_session: AsyncSession, seeded_editorinchief: User) -> TeiSchema:
    schema = TeiSchema(name="Test Schema", created_by=seeded_editorinchief.id)
    db_session.add(schema)
    await db_session.flush()
    return schema


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_schemas_authenticated(
    client: AsyncClient, seeded_user: User, seeded_schema: TeiSchema
) -> None:
    """Any authenticated user can list schemas."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/schemas", headers=_auth(token))
    assert res.status_code == 200
    names = [s["name"] for s in res.json()["data"]]
    assert "Test Schema" in names


@pytest.mark.asyncio
async def test_list_schemas_unauthenticated_returns_401(client: AsyncClient) -> None:
    res = await client.get("/api/v1/schemas")
    assert res.status_code == 401


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_schema_as_editorinchief(
    client: AsyncClient, seeded_editorinchief: User
) -> None:
    """EditorInChief can create a new schema entry."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.post(
        "/api/v1/schemas",
        headers=_auth(token),
        json={"name": "New Schema"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["name"] == "New Schema"


@pytest.mark.asyncio
async def test_create_schema_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor (level 2) cannot create schemas — requires EditorInChief+."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/schemas", headers=_auth(token), json={"name": "Forbidden"}
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_create_schema_with_empty_name_returns_422(
    client: AsyncClient, seeded_editorinchief: User
) -> None:
    """Creating a schema with a blank name returns 422 (Pydantic validation)."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.post(
        "/api/v1/schemas",
        headers=_auth(token),
        json={"name": "   "},
    )
    assert res.status_code == 422


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_schema_as_editorinchief(
    client: AsyncClient,
    seeded_editorinchief: User,
    seeded_schema: TeiSchema,
    tmp_path: Path,
) -> None:
    """EditorInChief can delete a schema."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    with patch("app.services.schemas.settings") as mock_settings:
        mock_settings.schemas_dir = tmp_path
        res = await client.delete(
            f"/api/v1/schemas/{seeded_schema.id}", headers=_auth(token)
        )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_delete_nonexistent_schema_returns_404(
    client: AsyncClient, seeded_editorinchief: User
) -> None:
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    res = await client.delete(
        f"/api/v1/schemas/{uuid.uuid4()}", headers=_auth(token)
    )
    assert res.status_code == 404


# ── Upload validation file ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_validation_file_as_editorinchief(
    client: AsyncClient,
    seeded_editorinchief: User,
    seeded_schema: TeiSchema,
    tmp_path: Path,
) -> None:
    """EditorInChief can upload a validation schema file."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    rng_content = b'<grammar xmlns="http://relaxng.org/ns/structure/1.0"><start><element name="doc"><text/></element></start></grammar>'
    with patch("app.services.schemas.settings") as mock_settings:
        mock_settings.schemas_dir = tmp_path
        res = await client.post(
            f"/api/v1/schemas/{seeded_schema.id}/upload-validation",
            headers=_auth(token),
            files={"file": ("schema.rng", BytesIO(rng_content), "application/xml")},
        )
    assert res.status_code == 200
    assert res.json()["data"]["validation_filename"] is not None


# ── Upload CM5 file ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_cm5_file_as_editorinchief(
    client: AsyncClient,
    seeded_editorinchief: User,
    seeded_schema: TeiSchema,
    tmp_path: Path,
) -> None:
    """EditorInChief can upload a CM5 autocomplete schema file."""
    token = await _login_as(client, EIC_USERNAME, EIC_PASSWORD)
    cm5_content = b'<?xml version="1.0"?><modespec xmlns="http://codemirror.net/5/addon/hint/xml-hint"/>'
    with patch("app.services.schemas.settings") as mock_settings:
        mock_settings.schemas_dir = tmp_path
        res = await client.post(
            f"/api/v1/schemas/{seeded_schema.id}/upload-cm5",
            headers=_auth(token),
            files={"file": ("cm5.xml", BytesIO(cm5_content), "application/xml")},
        )
    assert res.status_code == 200
    assert res.json()["data"]["cm5_filename"] is not None


# ── Get CM5 file ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_cm5_file_when_missing_returns_404(
    client: AsyncClient, seeded_user: User, seeded_schema: TeiSchema
) -> None:
    """Requesting the CM5 file for a schema with no CM5 returns 404."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        f"/api/v1/schemas/{seeded_schema.id}/cm5-file", headers=_auth(token)
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_cm5_file_as_authenticated_user(
    client: AsyncClient,
    seeded_user: User,
    seeded_editorinchief: User,
    seeded_schema: TeiSchema,
    tmp_path: Path,
) -> None:
    """Any authenticated user can download the CM5 file if it exists."""
    cm5_bytes = b'<?xml version="1.0"?><modespec/>'
    # Patch get_cm5_content to return bytes directly without filesystem access
    with patch(
        "app.services.schemas.get_cm5_content",
        new_callable=lambda: lambda *_: None,
    ):
        with patch(
            "app.routers.schemas.svc.get_cm5_content",
            new=AsyncMock(return_value=cm5_bytes),
        ):
            token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
            res = await client.get(
                f"/api/v1/schemas/{seeded_schema.id}/cm5-file", headers=_auth(token)
            )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/xml")
