import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting
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
async def seeded_setting(db_session: AsyncSession) -> SystemSetting:
    """A simple platform setting for testing."""
    setting = SystemSetting(key="platform_name", value="Test Platform")
    db_session.add(setting)
    await db_session.flush()
    return setting


# ── Public UI config ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ui_config_public(client: AsyncClient) -> None:
    """GET /settings/ui-config requires no authentication."""
    res = await client.get("/api/v1/settings/ui-config")
    assert res.status_code == 200
    assert "data" in res.json()


# ── List settings ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_settings_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_setting: SystemSetting
) -> None:
    """Admin can list all settings."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/settings", headers=_auth(token))
    assert res.status_code == 200
    keys = [s["key"] for s in res.json()["data"]]
    assert "platform_name" in keys


@pytest.mark.asyncio
async def test_list_settings_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Non-Admin cannot access the settings list."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/settings", headers=_auth(token))
    assert res.status_code == 403


# ── Get single setting ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_setting_by_key_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_setting: SystemSetting
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/settings/platform_name", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["key"] == "platform_name"


@pytest.mark.asyncio
async def test_get_nonexistent_setting_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get(
        "/api/v1/settings/does_not_exist", headers=_auth(token)
    )
    assert res.status_code == 404


# ── Update setting ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_setting_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_setting: SystemSetting
) -> None:
    """Admin can update a setting's value."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.patch(
        "/api/v1/settings/platform_name",
        headers=_auth(token),
        json={"value": "New Platform Name"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["value"] == "New Platform Name"


@pytest.mark.asyncio
async def test_update_setting_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: User, seeded_setting: SystemSetting
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.patch(
        "/api/v1/settings/platform_name",
        headers=_auth(token),
        json={"value": "Hacked"},
    )
    assert res.status_code == 403
