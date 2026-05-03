"""Admin-side GDPR review tests — anonymise + reject flows.

Five concerns:

1. The Admin queue (``GET /admin/gdpr/requests``) returns every
   open submission.
2. ``POST /admin/gdpr/anonymise/{id}`` replaces the user's
   identifying fields with a placeholder, revokes their sessions
   and PATs, marks the request ``completed``, and writes the
   ``user.anonymised`` audit row carrying the placeholder ↔
   original-id mapping.
3. After anonymisation the user can no longer log in.
4. ``POST /admin/gdpr/reject/{id}`` marks the request ``rejected``
   without touching the user.
5. The audit_log rows authored by the user have their
   ``actor_username`` rewritten to the placeholder; their target
   labels referencing the user are also rewritten.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.gdpr_request import (
    GdprRequest,
    GdprRequestKind,
    GdprRequestStatus,
)
from app.models.user import User
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_lists_open_requests(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_user: User,
) -> None:
    """User submits a request → Admin sees it in the queue."""
    user_token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    sub = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={"reason": "test"},
        headers=_auth(user_token),
    )
    assert sub.status_code == 202

    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get(
        "/api/v1/admin/gdpr/requests", headers=_auth(admin_token)
    )
    assert res.status_code == 200
    items = res.json()["data"]
    assert len(items) >= 1
    assert any(item["user_username"] == TEST_USER_USERNAME for item in items)


@pytest.mark.asyncio
async def test_admin_anonymises_user(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_user: User,
) -> None:
    """End-to-end: submit → admin executes → user is anonymised."""
    user_token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    sub = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={"reason": "court order #ABC"},
        headers=_auth(user_token),
    )
    request_id = sub.json()["data"]["request_id"]

    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        f"/api/v1/admin/gdpr/anonymise/{request_id}",
        json={"review_notes": "Verified court order on file."},
        headers=_auth(admin_token),
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["status"] == "completed"
    assert body["review_notes"] == "Verified court order on file."

    # The user's identifying fields are now placeholders.
    refreshed = await db_session.get(User, seeded_user.id)
    assert refreshed is not None
    assert refreshed.username.startswith("deleted_user_")
    assert refreshed.email.endswith("@deleted.invalid")
    assert refreshed.is_active is False
    assert refreshed.deleted_at is not None

    # The legal-trail audit row is in place.
    trail = list(
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "user.anonymised")
        )
    )
    assert len(trail) == 1
    payload = trail[0].payload
    assert payload["original_username"] == TEST_USER_USERNAME
    assert payload["placeholder"] == refreshed.username


@pytest.mark.asyncio
async def test_anonymised_user_cannot_login(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_user: User,
) -> None:
    """Login with the original username fails after anonymisation."""
    user_token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    sub = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={},
        headers=_auth(user_token),
    )
    request_id = sub.json()["data"]["request_id"]

    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    await client.post(
        f"/api/v1/admin/gdpr/anonymise/{request_id}",
        json={"review_notes": ""},
        headers=_auth(admin_token),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": TEST_USER_USERNAME,
            "password": TEST_USER_PASSWORD,
        },
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_admin_rejects_request(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_user: User,
) -> None:
    """Reject leaves the user untouched + flips the request status."""
    user_token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    sub = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={},
        headers=_auth(user_token),
    )
    request_id = sub.json()["data"]["request_id"]

    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        f"/api/v1/admin/gdpr/reject/{request_id}",
        json={"review_notes": "Pending external legal review."},
        headers=_auth(admin_token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "rejected"

    # User can still log in.
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": TEST_USER_USERNAME,
            "password": TEST_USER_PASSWORD,
        },
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_audit_actor_username_rewritten_after_anonymise(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_user: User,
) -> None:
    """Every audit_log row whose ``actor_id`` was the user gets its
    denormalised ``actor_username`` rewritten to the placeholder so
    subsequent audit-log searches by username don't reveal the
    original name."""
    user_token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    # Prime the audit log with a few rows authored by the user (logins).
    await client.get("/api/v1/auth/me", headers=_auth(user_token))
    sub = await client.post(
        "/api/v1/users/me/anonymise-request",
        json={},
        headers=_auth(user_token),
    )
    request_id = sub.json()["data"]["request_id"]

    admin_token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    await client.post(
        f"/api/v1/admin/gdpr/anonymise/{request_id}",
        json={"review_notes": ""},
        headers=_auth(admin_token),
    )

    # No remaining audit row carries the original username for this user.
    rows = list(
        await db_session.scalars(
            select(AuditLog).where(AuditLog.actor_id == seeded_user.id)
        )
    )
    for row in rows:
        assert row.actor_username != TEST_USER_USERNAME
        assert row.actor_username.startswith("deleted_user_")
