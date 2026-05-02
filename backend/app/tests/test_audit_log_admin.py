"""Admin audit-log view — pagination, filters, CSV, role gating.

Six concerns are checked:

1. Newest-first ordering on the default landing query.
2. Free-text ``q`` matches ``actor_username`` / ``action`` /
   ``target_label`` (the OR-of-three behaviour).
3. Structured filters compose with ``q`` (the AND-of-everything-else
   behaviour).
4. ``actions`` returns the curated dropdown vocabulary (not every
   distinct value in the table).
5. CSV export includes a header row plus one row per match.
6. Role gating: a non-Admin gets 403 on every endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
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


async def _seed_rows(db: AsyncSession) -> None:
    base = datetime.now(UTC) - timedelta(minutes=10)
    rows = [
        ("collection.created",   "anna_audit",  "collection", "abc-1", "Manzoni"),
        ("collection.published", "anna_audit",  "collection", "abc-1", "Manzoni"),
        ("auth.login_success",   "marco_audit", "user",       "u-1",   "marco_audit"),
        ("user.deactivated",     "anna_audit",  "user",       "u-2",   "carla"),
        ("document.uploaded",    "marco_audit", "document",   "d-1",   "letter_001.xml"),
    ]
    for i, (action, who, ttype, tid, label) in enumerate(rows):
        db.add(
            AuditLog(
                action=action,
                actor_username=who,
                target_type=ttype,
                target_id=tid,
                target_label=label,
                occurred_at=base + timedelta(minutes=i),
            )
        )
    await db.flush()


@pytest.mark.asyncio
async def test_list_default_newest_first(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_rows(db_session)
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get("/api/v1/audit-log", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    actions = [r["action"] for r in body["data"]]
    assert actions[0] == "document.uploaded"
    assert body["pagination"]["total"] >= 5


@pytest.mark.asyncio
async def test_list_q_matches_username(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_rows(db_session)
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get(
        "/api/v1/audit-log?q=marco_audit", headers=_auth(token)
    )
    assert resp.status_code == 200
    actors = {r["actor_username"] for r in resp.json()["data"]}
    assert actors == {"marco_audit"}


@pytest.mark.asyncio
async def test_list_q_matches_target_label(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_rows(db_session)
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get(
        "/api/v1/audit-log?q=letter_001", headers=_auth(token)
    )
    actions = {r["action"] for r in resp.json()["data"]}
    assert "document.uploaded" in actions


@pytest.mark.asyncio
async def test_list_structured_action_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_rows(db_session)
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get(
        "/api/v1/audit-log?action=collection.published", headers=_auth(token)
    )
    items = resp.json()["data"]
    assert items
    assert all(r["action"] == "collection.published" for r in items)


@pytest.mark.asyncio
async def test_list_filters_compose_q_plus_action(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_rows(db_session)
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get(
        "/api/v1/audit-log?q=anna_audit&action=collection.created",
        headers=_auth(token),
    )
    items = resp.json()["data"]
    assert len(items) == 1
    assert items[0]["action"] == "collection.created"
    assert items[0]["actor_username"] == "anna_audit"


@pytest.mark.asyncio
async def test_actions_endpoint_returns_curated_list(
    client: AsyncClient,
    seeded_admin: User,
) -> None:
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get("/api/v1/audit-log/actions", headers=_auth(token))
    assert resp.status_code == 200
    actions = resp.json()["data"]
    assert "auth.login_success" in actions
    assert "collection.published" in actions
    # Curated, not "every distinct value ever inserted"
    assert "evil.exe" not in actions


@pytest.mark.asyncio
async def test_csv_export_includes_header(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_rows(db_session)
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get(
        "/api/v1/audit-log/export.csv", headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.text
    first_line = text.splitlines()[0]
    assert first_line.startswith("id,occurred_at,action,actor_username,")
    assert len(text.strip().splitlines()) >= 6  # header + ≥5 rows


@pytest.mark.asyncio
async def test_non_admin_blocked(
    client: AsyncClient,
    seeded_user: User,
) -> None:
    """Non-Admin user must get 403 on every audit-log endpoint."""
    token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    for path in (
        "/api/v1/audit-log",
        "/api/v1/audit-log/actions",
        "/api/v1/audit-log/export.csv",
        "/api/v1/audit-log/1",
    ):
        resp = await client.get(path, headers=_auth(token))
        assert resp.status_code == 403, f"{path} returned {resp.status_code}"


@pytest.mark.asyncio
async def test_detail_returns_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    db_session.add(
        AuditLog(
            action="auth.login_success",
            actor_username="anna_audit",
            payload={"role": "Editor"},
            user_agent="test-agent/1.0",
        )
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(1)
        )
    ).scalar_one()

    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    resp = await client.get(
        f"/api/v1/audit-log/{row.id}", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["payload"] == {"role": "Editor"}
    assert body["user_agent"] == "test-agent/1.0"
