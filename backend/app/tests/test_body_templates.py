import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_template import BodyTemplate
from app.models.user import User
from app.tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_USER_PASSWORD, TEST_USER_USERNAME


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
async def seeded_body_template(db_session: AsyncSession) -> BodyTemplate:
    tpl = BodyTemplate(label="Paragraph", snippet="<p>$CURSOR$</p>", is_native=False)
    db_session.add(tpl)
    await db_session.flush()
    return tpl


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_body_templates_as_authenticated_user(
    client: AsyncClient, seeded_user: User, seeded_body_template: BodyTemplate
) -> None:
    """Any authenticated user can list body templates."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/body-templates", headers=_auth(token))
    assert res.status_code == 200
    labels = [t["label"] for t in res.json()["data"]]
    assert "Paragraph" in labels


@pytest.mark.asyncio
async def test_list_body_templates_unauthenticated_returns_401(
    client: AsyncClient,
) -> None:
    res = await client.get("/api/v1/body-templates")
    assert res.status_code == 401


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_body_template_as_admin(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Admin can create a new body template."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/body-templates",
        headers=_auth(token),
        json={"label": "Header", "snippet": "<head/>"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["label"] == "Header"


@pytest.mark.asyncio
async def test_create_body_template_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor cannot create body templates (requires Admin)."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/body-templates",
        headers=_auth(token),
        json={"label": "Forbidden", "snippet": "<x/>"},
    )
    assert res.status_code == 403


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_body_template_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_body_template: BodyTemplate
) -> None:
    """Admin can patch a body template's label."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.patch(
        f"/api/v1/body-templates/{seeded_body_template.id}",
        headers=_auth(token),
        json={"label": "Updated Paragraph"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["label"] == "Updated Paragraph"


@pytest.mark.asyncio
async def test_update_nonexistent_body_template_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.patch(
        f"/api/v1/body-templates/{uuid.uuid4()}",
        headers=_auth(token),
        json={"label": "Ghost"},
    )
    assert res.status_code == 404


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_body_template_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_body_template: BodyTemplate
) -> None:
    """Admin can delete a body template."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/body-templates/{seeded_body_template.id}", headers=_auth(token)
    )
    assert res.status_code == 204
