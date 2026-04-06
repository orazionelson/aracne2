import pytest
from httpx import AsyncClient

from app.models.user import User
from app.tests.conftest import TEST_USER_PASSWORD, TEST_USER_USERNAME


# ── Helper ────────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient) -> tuple[str, str]:
    """Log in as the seeded test user. Returns (access_token, username)."""
    res = await client.post("/api/v1/auth/login", json={
        "username_or_email": TEST_USER_USERNAME,
        "password": TEST_USER_PASSWORD,
    })
    assert res.status_code == 200
    return res.json()["data"]["access_token"], TEST_USER_USERNAME


# ── Happy-path tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, seeded_user: User) -> None:
    """Valid credentials return access_token in body and set refresh cookie."""
    res = await client.post("/api/v1/auth/login", json={
        "username_or_email": TEST_USER_USERNAME,
        "password": TEST_USER_PASSWORD,
    })
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body["data"]
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["user"]["username"] == TEST_USER_USERNAME
    assert "refresh_token" in res.cookies


@pytest.mark.asyncio
async def test_me_returns_user_data(client: AsyncClient, seeded_user: User) -> None:
    """GET /auth/me with valid token returns current user profile."""
    access_token, username = await _login(client)
    res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["username"] == username
    assert data["role"] == "Editor"


@pytest.mark.asyncio
async def test_refresh_rotates_token(client: AsyncClient, seeded_user: User) -> None:
    """POST /auth/refresh issues a new access token and rotates the cookie."""
    access_token, _ = await _login(client)
    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 200
    new_token = res.json()["data"]["access_token"]
    assert new_token != access_token
    assert "refresh_token" in res.cookies


@pytest.mark.asyncio
async def test_password_change_success(client: AsyncClient, seeded_user: User) -> None:
    """Password change with correct current password returns 200."""
    access_token, _ = await _login(client)
    res = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": TEST_USER_PASSWORD, "new_password": "newpassword1"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["message"] == "Password changed successfully"


# ── Error-case tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_wrong_credentials(client: AsyncClient) -> None:
    """Login with wrong password returns 401 in Aracne2 error format."""
    res = await client.post("/api/v1/auth/login", json={
        "username_or_email": "nonexistent",
        "password": "wrong",
    })
    assert res.status_code == 401
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(client: AsyncClient) -> None:
    """POST /auth/refresh with no cookie returns 401."""
    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "MISSING_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    """GET /auth/me without Bearer token returns 401."""
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_password_change_without_token_returns_401(client: AsyncClient) -> None:
    """POST /auth/password/change without token returns 401."""
    res = await client.post("/api/v1/auth/password/change", json={
        "current_password": "old",
        "new_password": "newpassword1",
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_token_returns_200(client: AsyncClient) -> None:
    """POST /auth/logout is best-effort — returns 200 even without a token."""
    res = await client.post("/api/v1/auth/logout")
    assert res.status_code == 200
    assert res.json()["data"]["message"] == "Logged out successfully"
