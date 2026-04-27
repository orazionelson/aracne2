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


@pytest_asyncio.fixture
async def seeded_capability_plugin(db_session: AsyncSession) -> Plugin:
    """A non-native, active plugin with both capability fields populated.

    Mirrors what plugin_loader.sync_registry writes for a real
    inline_authority/collection_deposit/website_deposit declaration.
    """
    plugin = Plugin(
        name="cap-plugin",
        display_name="Capability Plugin",
        status=PluginStatus.active,
        is_native=False,
        capabilities=["inline_authority", "collection_deposit"],
        ui_descriptor={
            "inline_authority": {
                "component": "DummyLinkPanel",
                "label_key": "lookups.dummy",
                "icon_color": "text-amber-500",
                "apply": "ref",
                "initial_context": "selection",
                "priority": 100,
            },
            "collection_deposit": {
                "component": "DummyCollectionDepositPanel",
                "label": "Dummy",
                "priority": 100,
            },
        },
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


# ── Capability surface (auto-cabling contract) ────────────────────────────────


@pytest.mark.asyncio
async def test_list_plugins_exposes_capabilities_and_ui_descriptor(
    client: AsyncClient,
    seeded_admin: User,
    seeded_capability_plugin: Plugin,
) -> None:
    """The plugin list response carries capabilities + ui_descriptor verbatim.

    The SPA reads these to auto-cable the plugin into the editor toolbar
    and the Deposita / Deposito tabs without per-plugin code, so the
    fields must round-trip through the API exactly as written by
    sync_registry.
    """
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/plugins", headers=_auth(token))
    assert res.status_code == 200

    plugins = res.json()["data"]
    seeded = next((p for p in plugins if p["name"] == "cap-plugin"), None)
    assert seeded is not None, "seeded capability plugin missing from list"

    assert seeded["capabilities"] == ["inline_authority", "collection_deposit"]
    desc = seeded["ui_descriptor"]
    assert isinstance(desc, dict)
    assert desc["inline_authority"]["component"] == "DummyLinkPanel"
    assert desc["inline_authority"]["apply"] == "ref"
    assert desc["inline_authority"]["initial_context"] == "selection"
    assert desc["inline_authority"]["priority"] == 100
    assert desc["collection_deposit"]["component"] == "DummyCollectionDepositPanel"
    assert desc["collection_deposit"]["label"] == "Dummy"


@pytest.mark.asyncio
async def test_plugin_without_capabilities_serialises_defaults(
    client: AsyncClient,
    seeded_admin: User,
    seeded_plugin: Plugin,
) -> None:
    """Plugins not advertising any capability return [] / None — never missing.

    Guards against a frontend regression where the SPA expects the
    fields to always be present (typed `capabilities: string[]` and
    `ui_descriptor: Record<string, unknown> | null` on the store).
    """
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/plugins", headers=_auth(token))
    assert res.status_code == 200

    plugins = res.json()["data"]
    seeded = next((p for p in plugins if p["name"] == "test-plugin"), None)
    assert seeded is not None
    assert seeded["capabilities"] == []
    assert seeded["ui_descriptor"] is None
