import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.license import License
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
async def seeded_license(db_session: AsyncSession) -> License:
    lic = License(name="CC BY 4.0", target="https://creativecommons.org/licenses/by/4.0/")
    db_session.add(lic)
    await db_session.flush()
    return lic


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_licenses_as_authenticated_user(
    client: AsyncClient, seeded_user: User, seeded_license: License
) -> None:
    """Any authenticated user can list licenses."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/licenses", headers=_auth(token))
    assert res.status_code == 200
    names = [lic["name"] for lic in res.json()["data"]]
    assert "CC BY 4.0" in names


@pytest.mark.asyncio
async def test_list_licenses_unauthenticated_returns_401(
    client: AsyncClient,
) -> None:
    res = await client.get("/api/v1/licenses")
    assert res.status_code == 401


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_license_as_admin(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Admin can create a new license."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/licenses",
        headers=_auth(token),
        json={"name": "MIT", "target": "https://opensource.org/licenses/MIT"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["name"] == "MIT"


@pytest.mark.asyncio
async def test_create_license_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Non-Admin cannot create licenses."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/licenses",
        headers=_auth(token),
        json={"name": "GPL"},
    )
    assert res.status_code == 403


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_license_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_license: License
) -> None:
    """Admin can patch a license."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.patch(
        f"/api/v1/licenses/{seeded_license.id}",
        headers=_auth(token),
        json={"name": "CC BY 4.0 Updated"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "CC BY 4.0 Updated"


@pytest.mark.asyncio
async def test_update_nonexistent_license_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.patch(
        f"/api/v1/licenses/{uuid.uuid4()}",
        headers=_auth(token),
        json={"name": "Ghost License"},
    )
    assert res.status_code == 404


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_license_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_license: License
) -> None:
    """Admin can delete a license."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/licenses/{seeded_license.id}", headers=_auth(token)
    )
    assert res.status_code == 204
