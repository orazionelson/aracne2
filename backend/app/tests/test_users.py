import uuid

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
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


# ── List users ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_users_without_token_returns_401(client: AsyncClient) -> None:
    res = await client.get("/api/v1/users")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_users_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor (level 2) cannot access the user list — requires EiC+."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/users", headers=_auth(token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_users_as_admin(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Admin can list users; response contains pagination metadata."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/users", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert "data" in body
    assert "pagination" in body
    assert isinstance(body["data"], list)


# ── Create user ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_user_as_admin(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Admin can create a new user; password_hash must not appear in response."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newpassword1",
            "role": "Editor",
        },
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["username"] == "newuser"
    assert data["role"] == "Editor"
    assert "password_hash" not in str(res.json())
    assert "password" not in str(res.json())


@pytest.mark.asyncio
async def test_create_user_duplicate_username_returns_409(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Creating a user with an existing username returns 409."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={
            "username": TEST_USER_USERNAME,
            "email": "other@example.com",
            "password": "password1",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_create_user_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor cannot create users."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={
            "username": "other",
            "email": "other@example.com",
            "password": "password1",
        },
    )
    assert res.status_code == 403


# ── Get user detail ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_detail_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Admin can retrieve a specific user's detail."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get(
        f"/api/v1/users/{seeded_user.id}", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["data"]["username"] == TEST_USER_USERNAME


@pytest.mark.asyncio
async def test_get_nonexistent_user_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get(
        f"/api/v1/users/{uuid.uuid4()}", headers=_auth(token)
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


# ── Role management ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_role_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Admin can assign a new role to a user."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        f"/api/v1/users/{seeded_user.id}/roles",
        headers=_auth(token),
        json={"role_name": "Designer"},
    )
    assert res.status_code == 201
    roles = [r["role_name"] for r in res.json()["data"]["roles"]]
    assert "Designer" in roles


@pytest.mark.asyncio
async def test_assign_duplicate_role_returns_409(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Assigning a role the user already has returns 409."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        f"/api/v1/users/{seeded_user.id}/roles",
        headers=_auth(token),
        json={"role_name": "Editor"},  # seeded_user already has Editor
    )
    assert res.status_code == 409


# ── GDPR self-service ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_my_data(client: AsyncClient, seeded_user: User) -> None:
    """Authenticated user can export their own data.

    The payload reshape after the GDPR-posture rework: the export
    is a deep dict (profile + role_grants + sessions + audit_log +
    notifications + personal_access_tokens + …), not a thin
    UserExport. Verify a few invariants instead of an exact shape.
    """
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        "/api/v1/users/me/export", headers=_auth(token)
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["profile"]["username"] == TEST_USER_USERNAME
    assert "password_hash" not in str(res.json())
    assert "ip_address" not in str(res.json())
    # The rich payload includes the new admin-metadata sections.
    for key in ("role_grants", "sessions", "audit_log", "notifications", "gdpr_requests"):
        assert key in data


@pytest.mark.asyncio
async def test_anonymise_request_creates_pending_row(
    client: AsyncClient, seeded_user: User
) -> None:
    """User can submit an anonymisation request; account stays usable.

    Replaces the previous ``test_delete_my_account``: the
    self-service hard-delete path was removed in the GDPR-posture
    rework — see docs/reference/GDPR_POSTURE.md.
    """
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={"reason": "personal request"},
        headers=_auth(token),
    )
    assert res.status_code == 202
    body = res.json()["data"]
    assert body["status"] == "submitted"
    assert "request_id" in body

    # Account is still usable — login still works because the
    # anonymise action is mediated, not immediate.
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": TEST_USER_USERNAME,
            "password": TEST_USER_PASSWORD,
        },
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_anonymise_request_conflict_when_already_open(
    client: AsyncClient, seeded_user: User
) -> None:
    """A second submission while one is still open returns 409."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res1 = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={"reason": "first"},
        headers=_auth(token),
    )
    assert res1.status_code == 202
    res2 = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={"reason": "second"},
        headers=_auth(token),
    )
    assert res2.status_code == 409


# ── Update / soft-delete / role revocation ────────────────────────────────────


@pytest.mark.asyncio
async def test_update_user_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Admin can update a user's display_name."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.patch(
        f"/api/v1/users/{seeded_user.id}",
        headers=_auth(token),
        json={"display_name": "Updated Name"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["display_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_user_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Admin can soft-delete a user; subsequent GET returns 404."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/users/{seeded_user.id}", headers=_auth(token)
    )
    assert res.status_code == 204
    get_res = await client.get(
        f"/api/v1/users/{seeded_user.id}", headers=_auth(token)
    )
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_remove_role_from_user_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Admin can revoke a role from a user."""
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/users/{seeded_user.id}/roles/Editor",
        headers=_auth(token),
    )
    assert res.status_code == 200
    roles = [r["role_name"] for r in res.json()["data"]["roles"]]
    assert "Editor" not in roles
