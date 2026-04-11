import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plugin import Plugin, PluginStatus
from app.models.user import User
from app.tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_USER_PASSWORD, TEST_USER_USERNAME


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_plugin(db_session: AsyncSession) -> Plugin:
    """A non-native, inactive plugin ready for activation."""
    plugin = Plugin(
        name="test-plugin",
        display_name="Test Plugin",
        status=PluginStatus.inactive,
        is_native=False,
    )
    db_session.add(plugin)
    await db_session.flush()
    return plugin


@pytest_asyncio.fixture
async def seeded_active_plugin(db_session: AsyncSession) -> Plugin:
    """A non-native plugin that is already active (needed for deactivate tests)."""
    plugin = Plugin(
        name="active-plugin",
        display_name="Active Plugin",
        status=PluginStatus.active,
        is_native=False,
    )
    db_session.add(plugin)
    await db_session.flush()
    return plugin


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


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_plugins_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_plugin: Plugin
) -> None:
    """Admin can list all registered plugins."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/plugins", headers=_auth(token))
    assert res.status_code == 200
    assert isinstance(res.json()["data"], list)


@pytest.mark.asyncio
async def test_list_plugins_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Non-Admin cannot list plugins."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/plugins", headers=_auth(token))
    assert res.status_code == 403


# ── Activate ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_plugin_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_plugin: Plugin
) -> None:
    """Admin can activate an inactive plugin."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        f"/api/v1/plugins/{seeded_plugin.name}/activate", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "active"


@pytest.mark.asyncio
async def test_activate_nonexistent_plugin_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/plugins/nonexistent/activate", headers=_auth(token)
    )
    assert res.status_code == 404


# ── Deactivate ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deactivate_plugin_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_active_plugin: Plugin
) -> None:
    """Admin can deactivate an active plugin."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        f"/api/v1/plugins/{seeded_active_plugin.name}/deactivate", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "inactive"


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_plugin_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_plugin: Plugin
) -> None:
    """Admin can delete an inactive plugin; subsequent activate returns 404."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/plugins/{seeded_plugin.name}", headers=_auth(token)
    )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_delete_nonexistent_plugin_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        "/api/v1/plugins/nonexistent", headers=_auth(token)
    )
    assert res.status_code == 404
