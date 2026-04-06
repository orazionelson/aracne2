# PHASE 03 — User Management: CRUD, roles, GDPR endpoints
# Prerequisite: CLAUDE.md loaded. Phases 01a–02 complete and passing.
# Goal: Admin/EiC can list and manage users; users can export and delete
#       their own account; role assignment/revocation by Admin.
#
# No new migrations are required — all tables (users, roles, user_roles)
# were created in Phase 01.

---

## Overview

Three groups of endpoints:

| Group              | Prefix          | ACL                  |
|--------------------|-----------------|----------------------|
| User list/detail   | `/users`        | [EiC+] read, [A] write |
| Role management    | `/users/{id}/roles` | [EiC+] read, [A] write |
| Self-service GDPR  | `/users/me/...` | [auth]               |

**Privacy constraints (non-negotiable):**
- `password_hash` must never appear in any response.
- `ip_address`, `user_agent` from sessions/audit_log must never appear in any response.
- Soft-delete: `DELETE /users/{id}` sets `deleted_at`, does not remove the row.
  Hard-delete cascades automatically via PostgreSQL FK when GDPR deletion is
  requested via `DELETE /users/me`.

**Audit log entries** (write to `audit_log` in every sensitive operation):

| Action                  | Trigger                          |
|-------------------------|----------------------------------|
| `user.created`          | Admin creates a user             |
| `user.updated`          | Admin patches a user             |
| `user.deactivated`      | Admin sets `is_active = false`   |
| `user.soft_deleted`     | Admin soft-deletes a user        |
| `user.role_assigned`    | Admin assigns a role             |
| `user.role_revoked`     | Admin revokes a role             |
| `user.self_deleted`     | User deletes their own account   |
| `user.data_exported`    | User exports their personal data |

Write audit entries in the **service layer**, not in the router.
Use the helper `_audit(db, action, actor, target_user, payload)` defined below.

---

## File: backend/app/schemas/users.py

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class RoleInfo(BaseModel):
    """Single active role entry as returned in user detail."""
    role_name: str
    assigned_at: datetime

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Safe user representation — no password_hash, ip_address or user_agent."""
    id: uuid.UUID
    username: str
    email: str
    display_name: str | None
    preferred_lang: str
    is_active: bool
    is_verified: bool
    role: str           # highest active role (same derivation as JWT)
    roles: list[RoleInfo]  # all active role assignments
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    deleted_at: datetime | None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    """Payload for Admin creating a new user."""
    username: str
    email: EmailStr
    password: str
    display_name: str | None = None
    preferred_lang: str = "it"
    role: str = "User"   # role to assign (must be a valid RoleName)

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def username_no_spaces(cls, v: str) -> str:
        if not v.strip() or " " in v:
            raise ValueError("Username must not contain spaces")
        return v.strip()

    @field_validator("preferred_lang")
    @classmethod
    def lang_valid(cls, v: str) -> str:
        if v not in ("it", "en"):
            raise ValueError("preferred_lang must be 'it' or 'en'")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        valid = {"Admin", "EditorInChief", "Designer", "Editor", "User"}
        if v not in valid:
            raise ValueError(f"role must be one of: {', '.join(sorted(valid))}")
        return v


class UserUpdate(BaseModel):
    """Payload for Admin patching a user. All fields optional."""
    email: EmailStr | None = None
    display_name: str | None = None
    preferred_lang: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None

    @field_validator("preferred_lang")
    @classmethod
    def lang_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("it", "en"):
            raise ValueError("preferred_lang must be 'it' or 'en'")
        return v


class RoleAssignRequest(BaseModel):
    """Payload for assigning a role to a user."""
    role_name: str

    @field_validator("role_name")
    @classmethod
    def role_valid(cls, v: str) -> str:
        valid = {"Admin", "EditorInChief", "Designer", "Editor", "User"}
        if v not in valid:
            raise ValueError(f"role_name must be one of: {', '.join(sorted(valid))}")
        return v


class UserExport(BaseModel):
    """Personal data export for GDPR art. 20."""
    id: str
    username: str
    email: str
    display_name: str | None
    preferred_lang: str
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None
    active_roles: list[str]
    active_sessions_count: int  # count only — no ip/ua details
```

---

## File: backend/app/services/users.py

Business logic only — no FastAPI imports.

```python
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, AuthorizationError
from app.core.password import hash_password
from app.models.audit_log import AuditLog
from app.models.role import Role, UserRole
from app.models.session import Session
from app.models.user import User
from app.schemas.users import UserCreate, UserExport, UserResponse, UserUpdate

logger = structlog.get_logger()

ROLE_LEVEL: dict[str, int] = {
    "Admin": 4, "EditorInChief": 3,
    "Designer": 2, "Editor": 2, "User": 1,
}


def _now() -> datetime:
    return datetime.now(UTC)


async def _audit(
    db: AsyncSession,
    action: str,
    actor: User,
    target: User,
    payload: dict[str, object] | None = None,
) -> None:
    db.add(AuditLog(
        action=action,
        actor_id=actor.id,
        actor_username=actor.username,
        target_type="user",
        target_id=str(target.id),
        target_label=target.username,
        payload=payload,
    ))


async def _get_active_roles(db: AsyncSession, user_id: uuid.UUID) -> list[UserRole]:
    stmt = (
        select(UserRole)
        .where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None))
    )
    return list(await db.scalars(stmt))


async def _highest_role(db: AsyncSession, user_id: uuid.UUID) -> str:
    from app.models.role import Role as _Role
    stmt = (
        select(_Role.name)
        .join(UserRole, UserRole.role_id == _Role.id)
        .where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None))
    )
    roles = list(await db.scalars(stmt))
    if not roles:
        return "User"
    return max(roles, key=lambda r: ROLE_LEVEL.get(str(r), 0))


async def _build_response(db: AsyncSession, user: User) -> UserResponse:
    """Build a UserResponse from an ORM User instance."""
    active_user_roles = await _get_active_roles(db, user.id)
    role_names_stmt = (
        select(Role.name, UserRole.assigned_at)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, UserRole.revoked_at.is_(None))
    )
    rows = list(await db.execute(role_names_stmt))
    from app.schemas.users import RoleInfo
    role_infos = [RoleInfo(role_name=str(r[0]), assigned_at=r[1]) for r in rows]
    highest = max(
        (str(r[0]) for r in rows),
        key=lambda r: ROLE_LEVEL.get(r, 0),
        default="User",
    )
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        preferred_lang=user.preferred_lang,
        is_active=user.is_active,
        is_verified=user.is_verified,
        role=highest,
        roles=role_infos,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        deleted_at=user.deleted_at,
    )


async def list_users(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    include_deleted: bool = False,
) -> tuple[list[UserResponse], int]:
    """
    Return (users, total_count) for the given filters.
    include_deleted=True is only meaningful for Admin callers (enforced in router).
    """
    stmt = select(User)
    if not include_deleted:
        stmt = stmt.where(User.deleted_at.is_(None))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(User.username.ilike(pattern), User.email.ilike(pattern))
        )
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if role:
        stmt = stmt.join(UserRole, UserRole.user_id == User.id).join(
            Role, Role.id == UserRole.role_id
        ).where(UserRole.revoked_at.is_(None), Role.name == role)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(User.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    users = list(await db.scalars(stmt))
    responses = [await _build_response(db, u) for u in users]
    return responses, total


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> UserResponse:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(message="User not found")
    return await _build_response(db, user)


async def create_user(
    db: AsyncSession,
    body: UserCreate,
    actor: User,
) -> UserResponse:
    # Uniqueness checks
    existing_username = await db.scalar(
        select(User).where(User.username == body.username)
    )
    if existing_username:
        raise ConflictError(message="Username already taken")
    existing_email = await db.scalar(
        select(User).where(User.email == body.email)
    )
    if existing_email:
        raise ConflictError(message="Email already registered")

    user = User(
        username=body.username,
        email=str(body.email),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        preferred_lang=body.preferred_lang,
        is_active=True,
        is_verified=True,  # Admin-created accounts are pre-verified
    )
    db.add(user)
    await db.flush()

    # The DB trigger fn_assign_default_role inserts a 'User' role automatically.
    # If a different role was requested, revoke the default and assign the requested one.
    if body.role != "User":
        default_ur = await db.scalar(
            select(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user.id, Role.name == "User", UserRole.revoked_at.is_(None))
        )
        if default_ur:
            default_ur.revoked_at = _now()
            default_ur.revoked_by = actor.id

        target_role = await db.scalar(select(Role).where(Role.name == body.role))
        if not target_role:
            raise NotFoundError(message=f"Role '{body.role}' not found")
        db.add(UserRole(user_id=user.id, role_id=target_role.id, assigned_by=actor.id))
        await db.flush()

    await _audit(db, "user.created", actor, user, {"role": body.role})
    logger.info("user_created", actor=actor.username, target=user.username)
    return await _build_response(db, user)


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    body: UserUpdate,
    actor: User,
) -> UserResponse:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(message="User not found")

    if body.email is not None and str(body.email) != user.email:
        existing = await db.scalar(select(User).where(User.email == str(body.email)))
        if existing:
            raise ConflictError(message="Email already registered")
        user.email = str(body.email)

    changed: dict[str, object] = {}
    if body.display_name is not None:
        user.display_name = body.display_name
        changed["display_name"] = body.display_name
    if body.preferred_lang is not None:
        user.preferred_lang = body.preferred_lang
        changed["preferred_lang"] = body.preferred_lang
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        changed["is_active"] = body.is_active
        if not body.is_active:
            # Revoke all active sessions immediately
            sessions = list(await db.scalars(
                select(Session).where(
                    Session.user_id == user_id, Session.revoked_at.is_(None)
                )
            ))
            for s in sessions:
                s.revoked_at = _now()
                s.revoked_reason = "user_deactivated"
    if body.is_verified is not None:
        user.is_verified = body.is_verified
        changed["is_verified"] = body.is_verified

    action = "user.deactivated" if changed.get("is_active") is False else "user.updated"
    await _audit(db, action, actor, user, changed if changed else None)
    logger.info("user_updated", actor=actor.username, target=user.username, changes=list(changed.keys()))
    return await _build_response(db, user)


async def soft_delete_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor: User,
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(message="User not found")
    if user.deleted_at is not None:
        raise ConflictError(message="User is already deleted")
    if user.id == actor.id:
        raise AuthorizationError(message="Cannot delete your own account via this endpoint")

    user.deleted_at = _now()
    user.is_active = False

    sessions = list(await db.scalars(
        select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    ))
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "user_deleted"

    await _audit(db, "user.soft_deleted", actor, user)
    logger.info("user_soft_deleted", actor=actor.username, target=user.username)


async def assign_role(
    db: AsyncSession,
    user_id: uuid.UUID,
    role_name: str,
    actor: User,
) -> UserResponse:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(message="User not found")

    role = await db.scalar(select(Role).where(Role.name == role_name))
    if not role:
        raise NotFoundError(message=f"Role '{role_name}' not found")

    # Check for active duplicate
    existing = await db.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
            UserRole.revoked_at.is_(None),
        )
    )
    if existing:
        raise ConflictError(message=f"User already has role '{role_name}'")

    db.add(UserRole(user_id=user_id, role_id=role.id, assigned_by=actor.id))

    # Invalidate sessions so the next refresh picks up the new role
    sessions = list(await db.scalars(
        select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    ))
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "role_changed"

    await _audit(db, "user.role_assigned", actor, user, {"role": role_name})
    logger.info("role_assigned", actor=actor.username, target=user.username, role=role_name)
    return await _build_response(db, user)


async def revoke_role(
    db: AsyncSession,
    user_id: uuid.UUID,
    role_name: str,
    actor: User,
) -> UserResponse:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(message="User not found")

    role = await db.scalar(select(Role).where(Role.name == role_name))
    if not role:
        raise NotFoundError(message=f"Role '{role_name}' not found")

    user_role = await db.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
            UserRole.revoked_at.is_(None),
        )
    )
    if not user_role:
        raise NotFoundError(message=f"User does not have active role '{role_name}'")

    user_role.revoked_at = _now()
    user_role.revoked_by = actor.id

    # Invalidate sessions so the next refresh picks up the role change
    sessions = list(await db.scalars(
        select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    ))
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "role_changed"

    await _audit(db, "user.role_revoked", actor, user, {"role": role_name})
    logger.info("role_revoked", actor=actor.username, target=user.username, role=role_name)
    return await _build_response(db, user)


async def export_my_data(db: AsyncSession, user: User) -> UserExport:
    """Return personal data for GDPR art. 20 export — no ip/ua fields."""
    active_roles_stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, UserRole.revoked_at.is_(None))
    )
    active_roles = [str(r) for r in await db.scalars(active_roles_stmt)]

    active_sessions_count = await db.scalar(
        select(func.count()).where(
            Session.user_id == user.id, Session.revoked_at.is_(None)
        )
    ) or 0

    await _audit(db, "user.data_exported", user, user)
    return UserExport(
        id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        preferred_lang=user.preferred_lang,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        active_roles=active_roles,
        active_sessions_count=active_sessions_count,
    )


async def delete_my_account(db: AsyncSession, user: User) -> None:
    """
    Hard-delete the calling user's account (GDPR art. 17).
    Cascades to sessions and user_roles via FK ON DELETE CASCADE.
    Sets actor_id = NULL in audit_log via FK ON DELETE SET NULL.
    """
    # Revoke sessions first so the access token is immediately invalid
    sessions = list(await db.scalars(
        select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    ))
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "account_deleted"

    # Write audit entry BEFORE deleting (actor_id will be set to NULL on cascade)
    db.add(AuditLog(
        action="user.self_deleted",
        actor_id=user.id,
        actor_username=user.username,
        target_type="user",
        target_id=str(user.id),
        target_label=user.username,
    ))
    await db.flush()

    await db.delete(user)
    logger.info("user_self_deleted", username=user.username)
```

---

## File: backend/app/routers/users.py

```python
import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user, require_role
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.users import (
    RoleAssignRequest,
    UserCreate,
    UserExport,
    UserResponse,
    UserUpdate,
)
from app.services.users import (
    assign_role,
    create_user,
    delete_my_account,
    export_my_data,
    get_user,
    list_users,
    revoke_role,
    soft_delete_user,
    update_user,
)

router = APIRouter(prefix="/users", tags=["users"])


# ── Self-service (GDPR) ───────────────────────────────────────────────────────

@router.get("/me/export")
async def export_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserExport]:
    data = await export_my_data(db, current_user)
    return DataResponse(data=data)


@router.delete("/me", status_code=204)
async def delete_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_my_account(db, current_user)


# ── Admin/EiC user management ─────────────────────────────────────────────────

@router.get("")
async def users_list(
    current_user: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    include_deleted: bool = Query(default=False),
) -> PaginatedResponse[UserResponse]:
    # include_deleted is Admin-only
    if include_deleted:
        from app.middleware.acl import ROLE_LEVEL
        caller_level = ROLE_LEVEL.get(request.state.role, 0)
        if caller_level < ROLE_LEVEL["Admin"]:
            include_deleted = False

    users, total = await list_users(
        db, page, per_page, search, role, is_active, include_deleted
    )
    return PaginatedResponse(
        data=users,
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


@router.get("/{user_id}")
async def user_detail(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await get_user(db, user_id)
    return DataResponse(data=data)


@router.post("", status_code=201)
async def user_create(
    body: UserCreate,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await create_user(db, body, current_user)
    return DataResponse(data=data)


@router.patch("/{user_id}")
async def user_update(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await update_user(db, user_id, body, current_user)
    return DataResponse(data=data)


@router.delete("/{user_id}", status_code=204)
async def user_soft_delete(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await soft_delete_user(db, user_id, current_user)


# ── Role management ───────────────────────────────────────────────────────────

@router.post("/{user_id}/roles", status_code=201)
async def role_assign(
    user_id: uuid.UUID,
    body: RoleAssignRequest,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await assign_role(db, user_id, body.role_name, current_user)
    return DataResponse(data=data)


@router.delete("/{user_id}/roles/{role_name}", status_code=200)
async def role_revoke(
    user_id: uuid.UUID,
    role_name: str,
    current_user: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UserResponse]:
    data = await revoke_role(db, user_id, role_name, current_user)
    return DataResponse(data=data)
```

---

## File: backend/app/core/exceptions.py (update)

Add two new exception classes. Keep all existing ones.

```python
class NotFoundError(PlatformException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(code="RESOURCE_NOT_FOUND", message=message, status_code=404)


class ConflictError(PlatformException):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(code="CONFLICT", message=message, status_code=409)
```

`AuthorizationError` already exists. Verify it has `status_code=403`.

---

## File: backend/app/main.py (update only)

```python
# Add alongside existing router imports:
from app.routers import auth, users

# Add alongside existing include_router calls:
app.include_router(users.router, prefix="/api/v1")
```

---

## File: backend/app/tests/test_users.py

```python
import pytest
from httpx import AsyncClient

from app.models.user import User
from app.tests.conftest import TEST_USER_PASSWORD, TEST_USER_USERNAME


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={
        "username_or_email": username,
        "password": password,
    })
    assert res.status_code == 200
    return res.json()["data"]["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── List users ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_users_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor (level 2) cannot access the user list (requires EiC+)."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/users", headers=_auth(token))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_users_without_token_returns_401(client: AsyncClient) -> None:
    res = await client.get("/api/v1/users")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_users_as_admin(
    client: AsyncClient, seeded_admin: User
) -> None:
    """Admin can list users; response contains pagination metadata."""
    token = await _login_as(client, "admin_test", "adminpass1")
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
    """Admin can create a new user."""
    token = await _login_as(client, "admin_test", "adminpass1")
    res = await client.post("/api/v1/users", headers=_auth(token), json={
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "newpassword1",
        "role": "Editor",
    })
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["username"] == "newuser"
    assert data["role"] == "Editor"
    assert "password_hash" not in str(res.json())


@pytest.mark.asyncio
async def test_create_user_duplicate_username_returns_409(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Creating a user with an existing username returns 409."""
    token = await _login_as(client, "admin_test", "adminpass1")
    res = await client.post("/api/v1/users", headers=_auth(token), json={
        "username": TEST_USER_USERNAME,
        "email": "other@example.com",
        "password": "password1",
    })
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_create_user_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor cannot create users."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post("/api/v1/users", headers=_auth(token), json={
        "username": "other",
        "email": "other@example.com",
        "password": "password1",
    })
    assert res.status_code == 403


# ── Get user detail ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_detail_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Admin can retrieve a specific user's detail."""
    token = await _login_as(client, "admin_test", "adminpass1")
    res = await client.get(f"/api/v1/users/{seeded_user.id}", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["username"] == TEST_USER_USERNAME


@pytest.mark.asyncio
async def test_get_nonexistent_user_returns_404(
    client: AsyncClient, seeded_admin: User
) -> None:
    import uuid
    token = await _login_as(client, "admin_test", "adminpass1")
    res = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=_auth(token))
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


# ── Role management ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_role_as_admin(
    client: AsyncClient, seeded_admin: User, seeded_user: User
) -> None:
    """Admin can assign a new role to a user."""
    token = await _login_as(client, "admin_test", "adminpass1")
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
    token = await _login_as(client, "admin_test", "adminpass1")
    res = await client.post(
        f"/api/v1/users/{seeded_user.id}/roles",
        headers=_auth(token),
        json={"role_name": "Editor"},  # seeded_user already has Editor
    )
    assert res.status_code == 409


# ── GDPR self-service ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_my_data(client: AsyncClient, seeded_user: User) -> None:
    """Authenticated user can export their own data."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/users/me/export", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["username"] == TEST_USER_USERNAME
    assert "password_hash" not in str(res.json())
    assert "ip_address" not in str(res.json())


@pytest.mark.asyncio
async def test_delete_my_account(client: AsyncClient, seeded_user: User) -> None:
    """User can delete their own account; subsequent login returns 401."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.delete("/api/v1/users/me", headers=_auth(token))
    assert res.status_code == 204
    # Login must now fail
    login = await client.post("/api/v1/auth/login", json={
        "username_or_email": TEST_USER_USERNAME,
        "password": TEST_USER_PASSWORD,
    })
    assert login.status_code == 401
```

---

## File: backend/app/tests/conftest.py (update)

Add a `seeded_admin` fixture after `seeded_user`. The admin fixture creates a
user with the Admin role directly (bypassing the DB trigger) using the same
approach as `seeded_user`.

```python
# Append to conftest.py

ADMIN_USERNAME = "admin_test"
ADMIN_PASSWORD = "adminpass1"

@pytest_asyncio.fixture
async def seeded_admin(db_session: AsyncSession, seeded_roles: list[str]) -> _User:
    user = _User(
        username=ADMIN_USERNAME,
        email="admin_test@example.com",
        password_hash=hash_password(ADMIN_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    admin_role = await db_session.scalar(
        select(_Role).where(_Role.name == "Admin")
    )
    db_session.add(UserRole(user_id=user.id, role_id=admin_role.id))
    await db_session.flush()
    return user
```

---

## Frontend: new views and routes

### New i18n keys (add to both `en.json` and `it.json`)

**en.json additions:**
```json
"users": {
  "title": "Users",
  "search_placeholder": "Search by username or email...",
  "create": "New user",
  "username": "Username",
  "email": "Email",
  "role": "Role",
  "status": "Status",
  "active": "Active",
  "inactive": "Inactive",
  "verified": "Verified",
  "not_verified": "Not verified",
  "created_at": "Created",
  "last_login": "Last login",
  "never": "Never",
  "edit": "Edit",
  "deactivate": "Deactivate",
  "activate": "Activate",
  "delete": "Delete",
  "confirm_delete": "This action cannot be undone. The user will be permanently removed.",
  "roles_title": "Roles",
  "assign_role": "Assign role",
  "revoke_role": "Revoke",
  "no_users": "No users found.",
  "password": "Password",
  "display_name": "Display name",
  "preferred_lang": "Language"
}
```

**it.json additions** (Italian equivalents — all keys must exist in both files).

### File: frontend/src/views/UsersView.vue

Paginated user list accessible to EditorInChief and above.
Shows a search input, a table with username/email/role/status/last login,
and (for Admin only) buttons for Edit and Delete.
Uses `apiClient.getPaginated<UserResponse>("/users", { params })`.

### File: frontend/src/views/UserDetailView.vue

Admin-only detail/edit view for a single user.
Shows the full `UserResponse` including role list.
Provides:
- A form to patch email, display_name, preferred_lang, is_active, is_verified.
- Role assignment: a select + "Assign" button; a "Revoke" button per active role.

### File: frontend/src/views/auth/ProfileView.vue (update)

Replace the WIP stub with the authenticated user's own data from the auth store.
Read-only view — no edit form in this phase.
Fields: username, email, display_name, role, preferred_lang, last_login_at.

### Router additions (frontend/src/router/index.ts)

```typescript
{
  path: "/users",
  name: "users",
  component: () => import("@/views/UsersView.vue"),
  meta: { requiresAuth: true, requiresMinRole: "EditorInChief" },
},
{
  path: "/users/:id",
  name: "user-detail",
  component: () => import("@/views/UserDetailView.vue"),
  meta: { requiresAuth: true, requiresMinRole: "Admin" },
},
```

---

## Checklist before committing

- [ ] `make test` passes (15 existing + 11 new = 26 total)
- [ ] `POST /api/v1/users` with Admin token → 201 + no password_hash in response
- [ ] `GET /api/v1/users` with Editor token → 403
- [ ] `GET /api/v1/users` with Admin token → 200 + pagination
- [ ] `POST /api/v1/users/{id}/roles` duplicate → 409
- [ ] `DELETE /api/v1/users/me` → 204 + subsequent login → 401
- [ ] `GET /api/v1/users/me/export` → 200 + no ip_address/user_agent in body
- [ ] `/users` route redirects to `/login` for unauthenticated users
- [ ] `/users` is not visible for Editor-level users (router guard)
- [ ] `make lint` clean
