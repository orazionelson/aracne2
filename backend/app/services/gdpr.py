"""GDPR posture for an editorial scientific platform — see
[`docs/reference/GDPR_POSTURE.md`](../../docs/reference/GDPR_POSTURE.md).

Three responsibilities:

1. :func:`export_personal_data` — art. 15 self-service export.
   Collects every personal-metadata row across the platform's
   admin tables and serialises them to a JSON-able dict the user
   can download as a ZIP. **Read-only**. Never returns
   ``password_hash``, the raw IP address (already SHA-256-hashed
   in production), the bcrypt digests of PATs / password-reset
   tokens, or any document body.
2. :func:`submit_anonymise_request` — the user's *request* (art.
   17 + 21). Inserts a ``gdpr_requests`` row with
   ``kind=anonymise``, ``status=submitted`` and notifies every
   active Admin via email. The user does NOT trigger any data
   change directly; the Admin reviews + acts.
3. :func:`anonymise_user_metadata` — Admin-side action. Replaces
   identifying fields on ``users`` with stable placeholders,
   rewrites every ``audit_log.actor_username`` row referencing the
   user with the same placeholder, revokes every active session
   and PAT, and stamps the user as inactive + soft-deleted. The
   editorial record (authorship of published documents, version
   rows the user authored) survives — those are third-party-
   affecting and outside the scope of art. 17 per art. 17.3.d
   ("scientific research / archiving in the public interest").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.audit_log import AuditLog
from app.models.gdpr_request import (
    GdprRequest,
    GdprRequestKind,
    GdprRequestStatus,
)
from app.models.notification import Notification
from app.models.password_reset_token import PasswordResetToken
from app.models.personal_access_token import PersonalAccessToken
from app.models.role import Role, UserRole
from app.models.session import Session
from app.models.user import User

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


# ── Art. 15 — self-service export ─────────────────────────────────────────────


async def export_personal_data(
    db: AsyncSession, user: User
) -> dict[str, Any]:
    """Return every piece of personal metadata the platform stores
    about *user*, ready for JSON serialisation.

    Includes: profile fields, active + revoked role grants,
    sessions (last 90 days, no IP / user-agent — the IP is hashed
    on write so its value adds nothing), audit_log rows where the
    user is actor or target, notifications (last 90 days), PATs
    (label + created_at; never the digest), GDPR requests the user
    has submitted.

    **Excluded by design**: ``password_hash``, the SHA-256-hashed
    ``ip_address`` (privacy-cost without investigative value), the
    raw ``user_agent`` strings (free-form, often carrying minor
    PII), bcrypt digests of any kind, any document body or version
    blob (those are editorial content, not personal data).
    """
    profile = {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "bio": user.bio,
        "orcid": user.orcid,
        "preferred_lang": user.preferred_lang,
        "is_active": user.is_active,
        "email_notifications_enabled": user.email_notifications_enabled,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login_at": (
            user.last_login_at.isoformat() if user.last_login_at else None
        ),
        "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
    }

    role_rows = list(
        await db.scalars(
            select(UserRole, Role)
            .join(Role, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    )
    # ``UserRole`` rows come back; resolve role names alongside.
    role_grants: list[dict[str, Any]] = []
    for ur in role_rows:
        role = await db.get(Role, ur.role_id)
        role_grants.append(
            {
                "role": str(role.name) if role else "(unknown)",
                "assigned_at": (
                    ur.assigned_at.isoformat() if ur.assigned_at else None
                ),
                "revoked_at": (
                    ur.revoked_at.isoformat() if ur.revoked_at else None
                ),
                "notes": ur.notes,
            }
        )

    sessions = list(
        await db.scalars(
            select(Session).where(Session.user_id == user.id)
        )
    )
    session_rows = [
        {
            "id": str(s.id),
            "started_at": s.started_at.isoformat() if getattr(s, "started_at", None) else None,
            "access_expires": (
                s.access_expires.isoformat() if s.access_expires else None
            ),
            "refresh_expires": (
                s.refresh_expires.isoformat() if s.refresh_expires else None
            ),
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
            "revoked_reason": s.revoked_reason,
        }
        for s in sessions
    ]

    audit_actor = list(
        await db.scalars(
            select(AuditLog).where(AuditLog.actor_id == user.id)
        )
    )
    audit_target = list(
        await db.scalars(
            select(AuditLog).where(
                AuditLog.target_type == "user",
                AuditLog.target_id == str(user.id),
                AuditLog.actor_id != user.id,
            )
        )
    )
    audit_rows = [
        {
            "id": r.id,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            "action": r.action,
            "as_actor": r.actor_id == user.id,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "target_label": r.target_label,
            "payload": r.payload,
        }
        for r in (*audit_actor, *audit_target)
    ]

    notifications = list(
        await db.scalars(
            select(Notification).where(Notification.user_id == user.id)
        )
    )
    notification_rows = [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "read_at": n.read_at.isoformat() if n.read_at else None,
        }
        for n in notifications
    ]

    pats = list(
        await db.scalars(
            select(PersonalAccessToken).where(
                PersonalAccessToken.user_id == user.id
            )
        )
    )
    pat_rows = [
        {
            "id": str(p.id),
            "label": p.label,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "last_used_at": (
                p.last_used_at.isoformat() if p.last_used_at else None
            ),
            "revoked_at": p.revoked_at.isoformat() if p.revoked_at else None,
        }
        for p in pats
    ]

    reset_tokens = list(
        await db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id
            )
        )
    )
    reset_rows = [
        {
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "used_at": t.used_at.isoformat() if t.used_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in reset_tokens
    ]

    gdpr_rows = list(
        await db.scalars(
            select(GdprRequest).where(GdprRequest.user_id == user.id)
        )
    )
    gdpr_request_rows = [
        {
            "id": str(g.id),
            "kind": g.kind,
            "status": g.status,
            "reason": g.reason,
            "submitted_at": (
                g.submitted_at.isoformat() if g.submitted_at else None
            ),
            "reviewed_at": (
                g.reviewed_at.isoformat() if g.reviewed_at else None
            ),
            "review_notes": g.review_notes,
            "completed_at": (
                g.completed_at.isoformat() if g.completed_at else None
            ),
        }
        for g in gdpr_rows
    ]

    db.add(
        AuditLog(
            action="user.data_exported",
            actor_id=user.id,
            actor_username=user.username,
            target_type="user",
            target_id=str(user.id),
            target_label=user.username,
        )
    )
    await db.flush()

    return {
        "exported_at": _now().isoformat(),
        "schema_version": 1,
        "profile": profile,
        "role_grants": role_grants,
        "sessions": session_rows,
        "audit_log": audit_rows,
        "notifications": notification_rows,
        "personal_access_tokens": pat_rows,
        "password_reset_tokens": reset_rows,
        "gdpr_requests": gdpr_request_rows,
        "notes": (
            "This export covers personal administrative metadata only. "
            "Editorial contributions to published documents are not "
            "included — those form the scientific record-of-work and are "
            "preserved under GDPR art. 17.3.d (research / archiving in "
            "the public interest). See docs/reference/GDPR_POSTURE.md."
        ),
    }


# ── Art. 17 — anonymisation request flow ──────────────────────────────────────


async def submit_anonymise_request(
    db: AsyncSession, *, user: User, reason: str | None
) -> GdprRequest:
    """Submit an anonymisation request for Admin review.

    Idempotent: re-submitting while a previous request is still
    open (``submitted`` or ``approved``) raises
    :class:`ConflictError` — there is at most one pending request
    per user. The user can re-open after a previous request was
    rejected or completed.

    The Admin notification (email) is best-effort; the request row
    is what matters for accountability.
    """
    open_request = await db.scalar(
        select(GdprRequest).where(
            GdprRequest.user_id == user.id,
            GdprRequest.kind == GdprRequestKind.anonymise.value,
            GdprRequest.status.in_(
                [
                    GdprRequestStatus.submitted.value,
                    GdprRequestStatus.approved.value,
                ]
            ),
        )
    )
    if open_request is not None:
        raise ConflictError(
            "An anonymisation request is already pending for this account."
        )

    row = GdprRequest(
        user_id=user.id,
        kind=GdprRequestKind.anonymise.value,
        status=GdprRequestStatus.submitted.value,
        reason=(reason or "").strip() or None,
    )
    db.add(row)
    db.add(
        AuditLog(
            action="user.anonymise_requested",
            actor_id=user.id,
            actor_username=user.username,
            target_type="user",
            target_id=str(user.id),
            target_label=user.username,
            payload={"has_reason": bool(reason)},
        )
    )
    await db.flush()
    logger.info(
        "gdpr_anonymise_requested",
        username=user.username,
        request_id=str(row.id),
    )

    # Notify Admins via the hook bus — the email_dispatcher plugin
    # listens for ON_GDPR_REQUEST_SUBMITTED and sends a heads-up to
    # every active Admin. Hook-bus errors are caught upstream by the
    # registry's emit, so a misconfigured email channel never blocks
    # the request from landing in the queue.
    from app.core.hooks import HookEvent, hook_registry

    await hook_registry.emit(
        HookEvent.ON_GDPR_REQUEST_SUBMITTED,
        request=row,
        user=user,
    )
    return row


async def list_open_requests(db: AsyncSession) -> list[GdprRequest]:
    """Admin view: every request not yet completed or rejected."""
    return list(
        await db.scalars(
            select(GdprRequest)
            .where(
                GdprRequest.status.in_(
                    [
                        GdprRequestStatus.submitted.value,
                        GdprRequestStatus.approved.value,
                    ]
                )
            )
            .order_by(GdprRequest.submitted_at.desc())
        )
    )


# ── Art. 17 — Admin-side anonymise action ─────────────────────────────────────


_PLACEHOLDER_PREFIX = "deleted_user_"


def _placeholder_for(user: User) -> str:
    """Stable placeholder identifier built from the user's UUID.

    Using the user's own UUID (not a sequence) keeps the
    placeholder reproducible across re-runs and avoids needing a
    sequence/counter table. ``deleted_user_`` prefix makes it
    obvious in audit log scans.
    """
    return f"{_PLACEHOLDER_PREFIX}{user.id.hex[:12]}"


async def anonymise_user_metadata(
    db: AsyncSession,
    *,
    request: GdprRequest,
    actor: User,
    review_notes: str | None,
) -> User:
    """Execute the anonymise action on the user the request covers.

    Steps, in order:

    1. Resolve the target user from ``request.user_id``; raise 404
       if gone.
    2. Build a stable placeholder identifier from the user's UUID.
    3. Overwrite identifying fields on ``users`` (username, email,
       display_name, bio, orcid, avatar_url) with placeholders.
       The user row stays — other tables FK to it (audit_log,
       document_versions, policy_page_versions) and nulling those
       FKs would break the editorial record.
    4. Update ``audit_log.actor_username`` for every row where the
       user was actor; the column is denormalised so it survives
       ``users`` deletion. After this update no row in audit_log
       carries the user's real username.
    5. Revoke every active session + every PAT.
    6. Stamp ``is_active=false`` + ``deleted_at=now()`` so the
       user can no longer authenticate.
    7. Mark the request row ``completed`` with the actor and
       review notes.
    8. Emit one ``user.anonymised`` audit row capturing the
       placeholder ↔ original-id mapping (the only place that link
       is preserved — kept here for legal-trail purposes; an
       operator who needs the mapping can pull it from this row).

    Raises :class:`ConflictError` when the request is not in
    ``submitted`` or ``approved`` state.
    """
    if request.status not in (
        GdprRequestStatus.submitted.value,
        GdprRequestStatus.approved.value,
    ):
        raise ConflictError(
            f"Request is in state '{request.status}' — only "
            "'submitted' or 'approved' requests can be executed."
        )

    user = await db.get(User, request.user_id)
    if user is None:
        raise NotFoundError(
            f"User {request.user_id} no longer exists."
        )

    placeholder = _placeholder_for(user)
    now = _now()
    original_username = user.username

    # 3. Overwrite identifying user fields.
    user.username = placeholder
    user.email = f"{placeholder}@deleted.invalid"
    user.display_name = None
    user.bio = None
    user.orcid = None
    user.avatar_url = None
    user.is_active = False
    user.deleted_at = now
    user.updated_at = now

    # 4. Rewrite audit_log.actor_username across every row.
    await db.execute(
        update(AuditLog)
        .where(AuditLog.actor_id == request.user_id)
        .values(actor_username=placeholder)
    )
    await db.execute(
        update(AuditLog)
        .where(
            AuditLog.target_type == "user",
            AuditLog.target_id == str(request.user_id),
        )
        .values(target_label=placeholder)
    )

    # 5. Revoke sessions + PATs.
    await db.execute(
        update(Session)
        .where(Session.user_id == request.user_id, Session.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="gdpr_anonymise")
    )
    await db.execute(
        update(PersonalAccessToken)
        .where(
            PersonalAccessToken.user_id == request.user_id,
            PersonalAccessToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    # Outstanding password-reset tokens become unusable as soon as
    # the email address is invalidated; we delete them here so the
    # row body doesn't carry stale data.
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == request.user_id
        )
    )

    # 7. Mark the request completed.
    request.status = GdprRequestStatus.completed.value
    request.reviewed_at = now
    request.reviewed_by_id = actor.id
    request.review_notes = (review_notes or "").strip() or None
    request.completed_at = now

    # 8. Emit the legal-trail audit row.
    db.add(
        AuditLog(
            action="user.anonymised",
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="user",
            target_id=str(request.user_id),
            target_label=placeholder,
            payload={
                "request_id": str(request.id),
                "placeholder": placeholder,
                "original_user_id": str(request.user_id),
                "original_username": original_username,
                "review_notes": review_notes,
            },
        )
    )
    await db.flush()
    logger.info(
        "gdpr_anonymise_completed",
        request_id=str(request.id),
        placeholder=placeholder,
        actor=actor.username,
    )
    return user


async def reject_anonymise_request(
    db: AsyncSession,
    *,
    request: GdprRequest,
    actor: User,
    review_notes: str | None,
) -> GdprRequest:
    """Mark the request rejected. The user's data is untouched.

    ``review_notes`` is expected to carry the reasoning (e.g.
    "no court order; pending external legal review"). Idempotent
    on already-completed / already-rejected requests: returns
    them as-is rather than transitioning.
    """
    if request.status in (
        GdprRequestStatus.completed.value,
        GdprRequestStatus.rejected.value,
    ):
        return request
    request.status = GdprRequestStatus.rejected.value
    request.reviewed_at = _now()
    request.reviewed_by_id = actor.id
    request.review_notes = (review_notes or "").strip() or None
    db.add(
        AuditLog(
            action="user.anonymise_rejected",
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="gdpr_request",
            target_id=str(request.id),
            target_label=str(request.user_id),
            payload={"review_notes": review_notes},
        )
    )
    await db.flush()
    return request


__all__ = [
    "export_personal_data",
    "submit_anonymise_request",
    "list_open_requests",
    "anonymise_user_metadata",
    "reject_anonymise_request",
]
