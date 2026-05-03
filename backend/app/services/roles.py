"""Capability-role primitives — Phase PP-B of Milestone 3.

Three responsibilities:

1. :func:`get_capability_holder` — return the (single) user who
   currently holds the named singleton capability role, or
   ``None``. The frontend's role-management UI uses this to show
   *"Current Policy Manager: [user X]"* with a Change button.
2. :func:`user_has_capability` — membership check used by
   :func:`require_capability` middleware. Admin always passes
   regardless of explicit assignment (Admin can do anything).
3. :func:`transfer_singleton_role` — transactional role transfer:
   revokes from the current holder (if any) and grants to the
   target user in the same transaction, with one audit row
   ``role.transferred`` capturing both legs.

Hierarchical role grants/revokes continue to live in
:mod:`app.routers.users` — capability roles get this dedicated
service so the singleton invariant has one canonical entry point.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.audit_log import AuditLog
from app.models.role import Role, RoleKind, UserRole
from app.models.user import User

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


async def get_capability_holder(
    db: AsyncSession, *, role_name: str
) -> User | None:
    """Return the user currently holding the named singleton capability,
    or ``None`` if the role is unassigned.

    Raises :class:`NotFoundError` if the role row does not exist
    (e.g. the migration that creates it has not run).
    """
    role = await db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise NotFoundError(f"Role '{role_name}' not found")
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(
            UserRole.role_id == role.id,
            UserRole.revoked_at.is_(None),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    return await db.scalar(stmt)


async def user_has_capability(
    db: AsyncSession, *, user: User, capability: str
) -> bool:
    """True when *user* has an active grant of *capability*.

    Admin users always pass — they own the platform; locking them
    out of a capability they manage would be more confusing than
    useful. For every other role the check is a simple ``user_roles``
    membership lookup.
    """
    # Admin shortcut. We re-resolve the user's hierarchical role
    # rather than trust a request-side ``role`` variable so this
    # function is safe to call from anywhere.
    admin_grant = await db.scalar(
        select(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            UserRole.revoked_at.is_(None),
            Role.name == "Admin",
        )
    )
    if admin_grant is not None:
        return True

    stmt = (
        select(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            UserRole.revoked_at.is_(None),
            Role.name == capability,
            Role.kind == RoleKind.capability.value,
        )
    )
    return (await db.scalar(stmt)) is not None


async def transfer_singleton_role(
    db: AsyncSession,
    *,
    role_name: str,
    target_user: User,
    actor: User,
) -> User:
    """Transactionally transfer a singleton capability role.

    Revokes the role from the current holder (if any) and grants
    it to *target_user*. Both legs run in the same transaction;
    the audit log captures the transfer as a single
    ``role.transferred`` row whose payload carries both sides.

    Raises :class:`ConflictError` when the role is not declared
    ``singleton``; the singleton invariant must be enforced at the
    schema level, not delegated to the caller. Idempotent on the
    "target already holds it" case — returns immediately without
    touching the DB.
    """
    role = await db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise NotFoundError(f"Role '{role_name}' not found")
    if not role.singleton:
        raise ConflictError(
            f"Role '{role_name}' is not a singleton role; "
            "use the regular grant endpoint instead."
        )

    current = await get_capability_holder(db, role_name=role_name)
    if current is not None and current.id == target_user.id:
        return target_user

    now = _now()
    if current is not None:
        # Revoke every active grant of this role for the previous
        # holder. There should only be one row given the singleton
        # invariant, but a defensive sweep is cheap and lets us
        # heal any pre-existing data drift.
        active = list(
            await db.scalars(
                select(UserRole).where(
                    UserRole.user_id == current.id,
                    UserRole.role_id == role.id,
                    UserRole.revoked_at.is_(None),
                )
            )
        )
        for ur in active:
            ur.revoked_at = now
            ur.revoked_by = actor.id

    db.add(
        UserRole(
            user_id=target_user.id,
            role_id=role.id,
            assigned_by=actor.id,
        )
    )
    db.add(
        AuditLog(
            action="role.transferred",
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="role",
            target_id=role_name,
            target_label=role_name,
            payload={
                "from_user_id": str(current.id) if current else None,
                "from_username": current.username if current else None,
                "to_user_id": str(target_user.id),
                "to_username": target_user.username,
            },
        )
    )
    await db.flush()
    logger.info(
        "capability_role_transferred",
        role=role_name,
        from_username=current.username if current else None,
        to_username=target_user.username,
    )
    return target_user


async def revoke_singleton_role(
    db: AsyncSession,
    *,
    role_name: str,
    actor: User,
) -> bool:
    """Revoke a singleton capability from its current holder, if any.

    Returns ``True`` if a holder was revoked, ``False`` if the role
    was already unassigned. Audit row ``role.revoked`` captures the
    operation; idempotent on the unassigned case.
    """
    role = await db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise NotFoundError(f"Role '{role_name}' not found")
    current = await get_capability_holder(db, role_name=role_name)
    if current is None:
        return False
    now = _now()
    active = list(
        await db.scalars(
            select(UserRole).where(
                UserRole.user_id == current.id,
                UserRole.role_id == role.id,
                UserRole.revoked_at.is_(None),
            )
        )
    )
    for ur in active:
        ur.revoked_at = now
        ur.revoked_by = actor.id
    db.add(
        AuditLog(
            action="role.revoked",
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="role",
            target_id=role_name,
            target_label=role_name,
            payload={
                "from_user_id": str(current.id),
                "from_username": current.username,
            },
        )
    )
    await db.flush()
    logger.info(
        "capability_role_revoked",
        role=role_name,
        from_username=current.username,
    )
    return True


__all__ = [
    "get_capability_holder",
    "user_has_capability",
    "transfer_singleton_role",
    "revoke_singleton_role",
]
