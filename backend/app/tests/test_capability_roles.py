"""Capability roles — singleton transfer, require_capability, REST.

Six concerns:

1. ``get_capability_holder`` returns ``None`` when the role is
   unassigned, the user when assigned.
2. ``user_has_capability`` returns False for a user without the
   grant; True for the holder; True for an Admin even without an
   explicit grant (Admin override).
3. ``transfer_singleton_role`` from an unassigned state grants
   the target and writes a single ``role.transferred`` audit row.
4. ``transfer_singleton_role`` from user A → B revokes A's row,
   grants B, writes one audit row whose payload carries both
   sides.
5. ``transfer_singleton_role`` is idempotent when the target
   already holds the role.
6. REST: ``GET / PUT / DELETE /admin/capabilities/PolicyManager``
   round trips for an Admin caller.
"""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password import hash_password
from app.models.audit_log import AuditLog
from app.models.role import Role, UserRole
from app.models.user import User
from app.services.roles import (
    get_capability_holder,
    revoke_singleton_role,
    transfer_singleton_role,
    user_has_capability,
)
from app.tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME


async def _seed_capability_roles(db: AsyncSession) -> Role:
    """Idempotently seed the PolicyManager role into the test DB.

    The conftest's seeded_roles fixture only seeds the five
    hierarchical roles; capability roles need explicit setup here.
    """
    existing = await db.scalar(select(Role).where(Role.name == "PolicyManager"))
    if existing is not None:
        existing.kind = "capability"
        existing.singleton = True
        await db.flush()
        return existing
    row = Role(
        name="PolicyManager",
        description="Edits institutional policy pages (singleton capability role)",
        kind="capability",
        singleton=True,
    )
    db.add(row)
    await db.flush()
    return row


async def _make_user(
    db: AsyncSession, username: str, *, with_user_role: bool = True
) -> User:
    user = User(
        username=username,
        email=f"{username}@example.test",
        password_hash=hash_password("dummy_test_password"),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    if with_user_role:
        # Give them the User hierarchical role so the existing
        # role-name->level lookup has something to return.
        from app.models.role import RoleName

        user_role_row = await db.scalar(
            select(Role).where(Role.name == RoleName.User)
        )
        if user_role_row is None:
            user_role_row = Role(name=RoleName.User, description="User", kind="hierarchical", singleton=False)
            db.add(user_role_row)
            await db.flush()
        db.add(UserRole(user_id=user.id, role_id=user_role_row.id))
        await db.flush()
    return user


# ── Service-level tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unassigned_holder_returns_none(
    db_session: AsyncSession, seeded_roles: list[str]
) -> None:
    await _seed_capability_roles(db_session)
    holder = await get_capability_holder(db_session, role_name="PolicyManager")
    assert holder is None


@pytest.mark.asyncio
async def test_transfer_from_unassigned(
    db_session: AsyncSession,
    seeded_roles: list[str],
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    target = await _make_user(db_session, "alice_pm")
    out = await transfer_singleton_role(
        db_session,
        role_name="PolicyManager",
        target_user=target,
        actor=seeded_admin,
    )
    assert out.id == target.id
    holder = await get_capability_holder(db_session, role_name="PolicyManager")
    assert holder is not None and holder.id == target.id
    audits = list(
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "role.transferred")
        )
    )
    assert len(audits) == 1
    assert audits[0].payload["from_user_id"] is None
    assert audits[0].payload["to_username"] == "alice_pm"


@pytest.mark.asyncio
async def test_transfer_a_to_b_revokes_a(
    db_session: AsyncSession,
    seeded_roles: list[str],
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    a = await _make_user(db_session, "alice_pm")
    b = await _make_user(db_session, "bob_pm")
    await transfer_singleton_role(
        db_session, role_name="PolicyManager", target_user=a, actor=seeded_admin
    )
    await transfer_singleton_role(
        db_session, role_name="PolicyManager", target_user=b, actor=seeded_admin
    )
    holder = await get_capability_holder(db_session, role_name="PolicyManager")
    assert holder is not None and holder.id == b.id
    # Alice's grant was revoked, not deleted.
    a_grants = list(
        await db_session.scalars(
            select(UserRole)
            .join(Role, UserRole.role_id == Role.id)
            .where(UserRole.user_id == a.id, Role.name == "PolicyManager")
        )
    )
    assert all(g.revoked_at is not None for g in a_grants)


@pytest.mark.asyncio
async def test_transfer_idempotent_when_already_holder(
    db_session: AsyncSession,
    seeded_roles: list[str],
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    a = await _make_user(db_session, "alice_pm")
    await transfer_singleton_role(
        db_session, role_name="PolicyManager", target_user=a, actor=seeded_admin
    )
    audit_count_before = len(
        list(
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "role.transferred")
            )
        )
    )
    await transfer_singleton_role(
        db_session, role_name="PolicyManager", target_user=a, actor=seeded_admin
    )
    audit_count_after = len(
        list(
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "role.transferred")
            )
        )
    )
    assert audit_count_after == audit_count_before


@pytest.mark.asyncio
async def test_user_has_capability_admin_override(
    db_session: AsyncSession,
    seeded_roles: list[str],
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    # No explicit grant; Admin still passes.
    assert await user_has_capability(
        db_session, user=seeded_admin, capability="PolicyManager"
    )


@pytest.mark.asyncio
async def test_user_has_capability_explicit_grant(
    db_session: AsyncSession,
    seeded_roles: list[str],
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    a = await _make_user(db_session, "alice_pm")
    assert not await user_has_capability(
        db_session, user=a, capability="PolicyManager"
    )
    await transfer_singleton_role(
        db_session, role_name="PolicyManager", target_user=a, actor=seeded_admin
    )
    assert await user_has_capability(
        db_session, user=a, capability="PolicyManager"
    )


@pytest.mark.asyncio
async def test_revoke_singleton_role(
    db_session: AsyncSession,
    seeded_roles: list[str],
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    a = await _make_user(db_session, "alice_pm")
    await transfer_singleton_role(
        db_session, role_name="PolicyManager", target_user=a, actor=seeded_admin
    )
    revoked = await revoke_singleton_role(
        db_session, role_name="PolicyManager", actor=seeded_admin
    )
    assert revoked is True
    holder = await get_capability_holder(db_session, role_name="PolicyManager")
    assert holder is None
    # Idempotent on re-call.
    revoked2 = await revoke_singleton_role(
        db_session, role_name="PolicyManager", actor=seeded_admin
    )
    assert revoked2 is False


# ── Endpoint tests ────────────────────────────────────────────────────────────


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
async def test_endpoint_get_unassigned(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get(
        "/api/v1/admin/capabilities/PolicyManager", headers=_auth(token)
    )
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["role_name"] == "PolicyManager"
    assert body["holder_user_id"] is None


@pytest.mark.asyncio
async def test_endpoint_put_then_get(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    target = await _make_user(db_session, "alice_pm")
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.put(
        "/api/v1/admin/capabilities/PolicyManager",
        json={"user_id": str(target.id)},
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["holder_username"] == "alice_pm"

    res2 = await client.get(
        "/api/v1/admin/capabilities/PolicyManager", headers=_auth(token)
    )
    assert res2.json()["data"]["holder_username"] == "alice_pm"


@pytest.mark.asyncio
async def test_endpoint_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_admin: User,
) -> None:
    await _seed_capability_roles(db_session)
    target = await _make_user(db_session, "alice_pm")
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    await client.put(
        "/api/v1/admin/capabilities/PolicyManager",
        json={"user_id": str(target.id)},
        headers=_auth(token),
    )
    res = await client.delete(
        "/api/v1/admin/capabilities/PolicyManager", headers=_auth(token)
    )
    assert res.status_code == 204

    res2 = await client.get(
        "/api/v1/admin/capabilities/PolicyManager", headers=_auth(token)
    )
    assert res2.json()["data"]["holder_user_id"] is None
