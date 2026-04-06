import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.core.hooks import HookEvent, hook_registry
from app.core.password import hash_password
from app.models.audit_log import AuditLog
from app.models.role import Role, UserRole
from app.models.session import Session
from app.models.user import User
from app.schemas.users import (
    RoleInfo,
    UserCreate,
    UserExport,
    UserResponse,
    UserUpdate,
)

logger = structlog.get_logger()

ROLE_LEVEL: dict[str, int] = {
    "Admin": 4,
    "EditorInChief": 3,
    "Designer": 2,
    "Editor": 2,
    "User": 1,
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
    db.add(
        AuditLog(
            action=action,
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="user",
            target_id=str(target.id),
            target_label=target.username,
            payload=payload,
        )
    )


async def _build_response(db: AsyncSession, user: User) -> UserResponse:
    """Build a UserResponse from an ORM User instance."""
    stmt = (
        select(Role.name, UserRole.assigned_at)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, UserRole.revoked_at.is_(None))
    )
    rows = list(await db.execute(stmt))
    role_infos = [RoleInfo(role_name=r[0].value, assigned_at=r[1]) for r in rows]
    highest = max(
        (r[0].value for r in rows),
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
    """Return (users, total_count) for the given filters."""
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
        stmt = (
            stmt.join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.revoked_at.is_(None), Role.name == role)
        )

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
    existing_username = await db.scalar(
        select(User).where(User.username == body.username)
    )
    if existing_username:
        raise ConflictError(message="Username already taken")

    existing_email = await db.scalar(
        select(User).where(User.email == str(body.email))
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
    # In tests (SQLite) the trigger does not run, so we always ensure the base
    # 'User' role exists then revoke it if a different role was requested.
    default_ur = await db.scalar(
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == user.id,
            Role.name == "User",
            UserRole.revoked_at.is_(None),
        )
    )
    if body.role != "User":
        if default_ur:
            default_ur.revoked_at = _now()
            default_ur.revoked_by = actor.id
        else:
            # SQLite / no trigger: assign then immediately revoke is not needed;
            # just skip to the target role below.
            pass

        target_role = await db.scalar(select(Role).where(Role.name == body.role))
        if not target_role:
            raise NotFoundError(message=f"Role '{body.role}' not found")
        db.add(UserRole(user_id=user.id, role_id=target_role.id, assigned_by=actor.id))
        await db.flush()
    elif not default_ur:
        # No trigger and role == "User": create the base role assignment.
        user_role_obj = await db.scalar(select(Role).where(Role.name == "User"))
        if user_role_obj:
            db.add(UserRole(user_id=user.id, role_id=user_role_obj.id, assigned_by=actor.id))
            await db.flush()

    await _audit(db, "user.created", actor, user, {"role": body.role})
    await hook_registry.emit(HookEvent.ON_USER_CREATED, db=db, actor=actor, user=user)
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
        existing = await db.scalar(
            select(User).where(User.email == str(body.email))
        )
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
            sessions = list(
                await db.scalars(
                    select(Session).where(
                        Session.user_id == user_id,
                        Session.revoked_at.is_(None),
                    )
                )
            )
            for s in sessions:
                s.revoked_at = _now()
                s.revoked_reason = "user_deactivated"
    if body.is_verified is not None:
        user.is_verified = body.is_verified
        changed["is_verified"] = body.is_verified

    action = (
        "user.deactivated"
        if changed.get("is_active") is False
        else "user.updated"
    )
    await _audit(db, action, actor, user, changed if changed else None)
    await hook_registry.emit(HookEvent.ON_USER_UPDATED, db=db, actor=actor, user=user, changes=changed)
    logger.info(
        "user_updated",
        actor=actor.username,
        target=user.username,
        changes=list(changed.keys()),
    )
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
        raise AuthorizationError(
            message="Cannot delete your own account via this endpoint"
        )

    user.deleted_at = _now()
    user.is_active = False

    sessions = list(
        await db.scalars(
            select(Session).where(
                Session.user_id == user_id, Session.revoked_at.is_(None)
            )
        )
    )
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "user_deleted"

    await _audit(db, "user.soft_deleted", actor, user)
    await hook_registry.emit(HookEvent.ON_USER_DELETED, db=db, actor=actor, user=user)
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
    sessions = list(
        await db.scalars(
            select(Session).where(
                Session.user_id == user_id, Session.revoked_at.is_(None)
            )
        )
    )
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "role_changed"

    await _audit(db, "user.role_assigned", actor, user, {"role": role_name})
    logger.info(
        "role_assigned", actor=actor.username, target=user.username, role=role_name
    )
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
        raise NotFoundError(
            message=f"User does not have active role '{role_name}'"
        )

    user_role.revoked_at = _now()
    user_role.revoked_by = actor.id

    sessions = list(
        await db.scalars(
            select(Session).where(
                Session.user_id == user_id, Session.revoked_at.is_(None)
            )
        )
    )
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "role_changed"

    await _audit(db, "user.role_revoked", actor, user, {"role": role_name})
    logger.info(
        "role_revoked", actor=actor.username, target=user.username, role=role_name
    )
    return await _build_response(db, user)


async def export_my_data(db: AsyncSession, user: User) -> UserExport:
    """Return personal data for GDPR art. 20 — no ip/ua fields."""
    active_roles_stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, UserRole.revoked_at.is_(None))
    )
    active_roles = [str(r) for r in await db.scalars(active_roles_stmt)]

    active_sessions_count = (
        await db.scalar(
            select(func.count()).where(
                Session.user_id == user.id,
                Session.revoked_at.is_(None),
            )
        )
        or 0
    )

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
        last_login_at=(
            user.last_login_at.isoformat() if user.last_login_at else None
        ),
        active_roles=active_roles,
        active_sessions_count=active_sessions_count,
    )


async def delete_my_account(db: AsyncSession, user: User) -> None:
    """
    Hard-delete the calling user's account (GDPR art. 17).
    Cascades to sessions and user_roles via FK ON DELETE CASCADE.
    Sets actor_id = NULL in audit_log via FK ON DELETE SET NULL.
    """
    # Write audit entry BEFORE deleting (actor_id will be NULL-ed on cascade)
    db.add(
        AuditLog(
            action="user.self_deleted",
            actor_id=user.id,
            actor_username=user.username,
            target_type="user",
            target_id=str(user.id),
            target_label=user.username,
        )
    )
    await db.flush()

    # Explicitly delete child rows before deletion — SQLite does not enforce
    # ON DELETE CASCADE without PRAGMA foreign_keys=ON, and SQLAlchemy's ORM
    # would otherwise try to SET NULL on NOT NULL FK columns (user_roles.user_id,
    # sessions.user_id), causing an IntegrityError.
    await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    await db.execute(delete(Session).where(Session.user_id == user.id))
    await db.flush()

    await db.delete(user)
    logger.info("user_self_deleted", username=user.username)
