import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User
from app.tests.conftest import TEST_USER_PASSWORD, TEST_USER_USERNAME


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
async def seeded_notification(
    db_session: AsyncSession, seeded_user: User
) -> Notification:
    """An unread notification belonging to seeded_user."""
    notif = Notification(
        user_id=seeded_user.id,
        type="test.notification",
        title="Test notification",
        body="This is a test body",
        is_read=False,
    )
    db_session.add(notif)
    await db_session.flush()
    return notif


# ── Unread count ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unread_count_returns_zero_for_new_user(
    client: AsyncClient, seeded_user: User
) -> None:
    """A fresh user with no notifications has unread count = 0."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/notifications/unread-count", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"] == 0


@pytest.mark.asyncio
async def test_unread_count_increments_with_notification(
    client: AsyncClient,
    seeded_user: User,
    seeded_notification: Notification,
) -> None:
    """Unread count reflects actual unread notifications."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/notifications/unread-count", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"] == 1


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_notifications_empty_for_new_user(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/notifications", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_list_notifications_unread_only(
    client: AsyncClient,
    seeded_user: User,
    seeded_notification: Notification,
) -> None:
    """Filtering by unread_only=true returns only unread notifications."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        "/api/v1/notifications?unread_only=true", headers=_auth(token)
    )
    assert res.status_code == 200
    items = res.json()["data"]
    assert len(items) == 1
    assert items[0]["is_read"] is False


# ── Mark read ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_notification_read(
    client: AsyncClient,
    seeded_user: User,
    seeded_notification: Notification,
) -> None:
    """PATCH /{id}/read marks the notification as read."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.patch(
        f"/api/v1/notifications/{seeded_notification.id}/read",
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["is_read"] is True


@pytest.mark.asyncio
async def test_mark_nonexistent_notification_returns_404(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.patch(
        "/api/v1/notifications/99999/read", headers=_auth(token)
    )
    assert res.status_code == 404


# ── Mark all read ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_all_read(
    client: AsyncClient,
    seeded_user: User,
    seeded_notification: Notification,
) -> None:
    """POST /read-all marks all unread notifications and returns the count."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post("/api/v1/notifications/read-all", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"] == 1


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_notification(
    client: AsyncClient,
    seeded_user: User,
    seeded_notification: Notification,
) -> None:
    """DELETE /{id} removes the notification."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.delete(
        f"/api/v1/notifications/{seeded_notification.id}", headers=_auth(token)
    )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_delete_other_users_notification_returns_403(
    client: AsyncClient,
    seeded_user: User,
    seeded_admin: User,
    seeded_notification: Notification,
) -> None:
    """Admin cannot delete another user's notification — notifications are personal."""
    from app.tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME

    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.delete(
        f"/api/v1/notifications/{seeded_notification.id}", headers=_auth(token)
    )
    assert res.status_code == 403
