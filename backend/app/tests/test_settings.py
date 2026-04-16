import io
from pathlib import Path
from unittest.mock import patch

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


# ── Logo upload / serve ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logo_file_returns_404_when_no_logo(
    client: AsyncClient, tmp_path: Path
) -> None:
    """GET /settings/logo/file returns 404 when no logo has been uploaded."""
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        res = await client.get("/api/v1/settings/logo/file")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_upload_logo_as_admin(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """Admin can upload a PNG logo; the response includes the serve URL."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        mock_settings.jwt_secret = "test-secret"
        res = await client.post(
            "/api/v1/settings/logo",
            headers=_auth(token),
            files={"file": ("logo.png", io.BytesIO(png_bytes), "image/png")},
        )
    assert res.status_code == 200
    assert res.json()["data"]["url"] == "/api/v1/settings/logo/file"


@pytest.mark.asyncio
async def test_upload_logo_with_invalid_extension_returns_422(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """Uploading a non-image file for the logo returns a 422 error."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        mock_settings.jwt_secret = "test-secret"
        res = await client.post(
            "/api/v1/settings/logo",
            headers=_auth(token),
            files={"file": ("document.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
    assert res.status_code == 422


# ── Homepage CSS upload / serve / delete ──────────────────────────────────────


@pytest.mark.asyncio
async def test_homepage_css_file_returns_404_when_no_css(
    client: AsyncClient, tmp_path: Path
) -> None:
    """GET /settings/homepage-css/file returns 404 when no CSS has been uploaded."""
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        res = await client.get("/api/v1/settings/homepage-css/file")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_upload_homepage_css_as_admin(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """Admin can upload a CSS file; the response includes the serve URL."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        res = await client.post(
            "/api/v1/settings/homepage-css",
            headers=_auth(token),
            files={"file": ("custom.css", io.BytesIO(b"body { color: red; }"), "text/css")},
        )
    assert res.status_code == 200
    assert res.json()["data"]["url"] == "/api/v1/settings/homepage-css/file"


@pytest.mark.asyncio
async def test_upload_homepage_css_with_wrong_extension_returns_422(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """Uploading a non-CSS file for the homepage stylesheet returns 422."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        res = await client.post(
            "/api/v1/settings/homepage-css",
            headers=_auth(token),
            files={"file": ("script.js", io.BytesIO(b"alert(1)"), "application/javascript")},
        )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_delete_homepage_css_when_none_returns_404(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """DELETE /settings/homepage-css returns 404 when no CSS has been uploaded."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        res = await client.delete(
            "/api/v1/settings/homepage-css", headers=_auth(token)
        )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_homepage_css_as_admin(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """Admin can delete an existing custom homepage CSS file."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    # Upload first, then delete.
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        await client.post(
            "/api/v1/settings/homepage-css",
            headers=_auth(token),
            files={"file": ("custom.css", io.BytesIO(b"body {}"), "text/css")},
        )
        res = await client.delete(
            "/api/v1/settings/homepage-css", headers=_auth(token)
        )
    assert res.status_code == 204


# ── Size guard: logo ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_logo_too_large_returns_422(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """Uploading a logo larger than 2 MB is rejected with 422."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    oversized = b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024 + 1)
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        mock_settings.jwt_secret = "test-secret"
        res = await client.post(
            "/api/v1/settings/logo",
            headers=_auth(token),
            files={"file": ("big.png", io.BytesIO(oversized), "image/png")},
        )
    assert res.status_code == 422


# ── Size guard: homepage CSS ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_homepage_css_too_large_returns_422(
    client: AsyncClient, seeded_admin: User, tmp_path: Path
) -> None:
    """Uploading a CSS file larger than 512 KB is rejected with 422."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    oversized = b"body { color: red; }" + b" " * (512 * 1024 + 1)
    with patch("app.services.settings.app_settings") as mock_settings:
        mock_settings.media_dir = tmp_path
        res = await client.post(
            "/api/v1/settings/homepage-css",
            headers=_auth(token),
            files={"file": ("big.css", io.BytesIO(oversized), "text/css")},
        )
    assert res.status_code == 422
