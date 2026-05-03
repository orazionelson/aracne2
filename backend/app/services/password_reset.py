"""Password reset service — Phase EM-C of the email channels feature.

Implements the public reset flow that the platform was missing:

- ``request_reset(db, email_or_username)``: lookup user by email OR
  username; if found, mint a 256-bit token, store its SHA-256 digest
  with ``expires_at = now + 24h``, and email the plaintext to the
  user as part of a reset URL. **Always returns None** — callers
  must not branch on existence to avoid timing / response-shape
  account enumeration.
- ``confirm_reset(db, token, new_password)``: lookup row by SHA-256;
  reject when missing / expired / already used; otherwise apply the
  new password, mark the row used, revoke every active session of
  the user, and audit the event.

The plaintext token is never persisted — only its SHA-256 digest. A
DB exfiltration cannot be used to reset accounts; the digest only lets
us *match* a presented plaintext, not derive one. Every failure mode
on confirm raises a single ``AuthenticationError(code=INVALID_RESET_TOKEN)``
so the client cannot tell which condition failed.

Rate-limit (10/min ``STRICT_LIMIT``) is applied at the router layer.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Final

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.password import hash_password
from app.models.audit_log import AuditLog
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User
from app.services.email import render, send_mail
from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()

#: How long a freshly minted reset link stays valid. Locked at 24h
#: per the design discussion — long enough to tolerate "I'll handle it
#: tomorrow", short enough that a leaked link is not a permanent risk.
TOKEN_TTL: Final[timedelta] = timedelta(hours=24)

#: Hours value rendered into the email body so the recipient sees a
#: human number rather than a raw timedelta.
TOKEN_TTL_HOURS: Final[int] = 24


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    """Normalise a datetime to tz-aware UTC.

    SQLite (used by the test runner) does not persist timezone info, so
    a value loaded from a ``DateTime(timezone=True)`` column comes back
    naive. PostgreSQL always returns tz-aware datetimes, so this is a
    no-op there. Same pattern as ``services/auth.py:_as_utc``.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


async def _resolve_default_lang(db: AsyncSession) -> str:
    return (await get_decrypted_setting(db, "default_language")) or "en"


async def _resolve_public_base_url(db: AsyncSession) -> str:
    return (await get_decrypted_setting(db, "public_base_url")) or ""


async def _lookup_user(db: AsyncSession, email_or_username: str) -> User | None:
    """Match a User by email OR username, case-insensitive on email.

    Returns None if no row matches; callers must NOT signal that to the
    HTTP client.
    """
    needle = email_or_username.strip()
    if not needle:
        return None
    stmt = select(User).where(
        or_(User.username == needle, User.email.ilike(needle))
    )
    return await db.scalar(stmt)


async def request_reset(db: AsyncSession, email_or_username: str) -> None:
    """Mint a one-time reset token and email it to the user.

    Always returns None — the caller never branches on user existence
    to avoid account enumeration through timing or response shape.
    Failures on the email side are logged but never propagated;
    Postfix logs are the operator's troubleshooting surface.
    """
    user = await _lookup_user(db, email_or_username)
    if user is None or not user.is_active:
        logger.info(
            "password_reset_request_missing_or_inactive",
            email_or_username_hash=hashlib.sha256(
                email_or_username.encode("utf-8")
            ).hexdigest()[:16],
        )
        return

    plaintext = secrets.token_urlsafe(32)
    digest = _hash_token(plaintext)
    expires_at = _now() + TOKEN_TTL

    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=digest,
            expires_at=expires_at,
        )
    )
    db.add(
        AuditLog(
            action="auth.password_reset_requested",
            actor_id=user.id,
            actor_username=user.username,
            target_type="user",
            target_id=str(user.id),
            target_label=user.username,
            payload={"expires_at": expires_at.isoformat()},
        )
    )
    await db.flush()

    base_url = await _resolve_public_base_url(db)
    reset_url = f"{base_url.rstrip('/')}/reset-password/{plaintext}"
    default_lang = await _resolve_default_lang(db)
    lang = (user.preferred_lang or default_lang).split("-")[0]

    try:
        subject, html, text = render(
            "password_reset",
            lang=lang,
            default_lang=default_lang,
            ctx={
                "recipient_display_name": user.display_name or user.username,
                "reset_url": reset_url,
                "expiry_hours": TOKEN_TTL_HOURS,
            },
        )
    except FileNotFoundError as exc:
        logger.error("password_reset_template_missing", error=str(exc))
        return
    await send_mail(db, to=user.email, subject=subject, html=html, text=text)


async def confirm_reset(
    db: AsyncSession, token: str, new_password: str
) -> None:
    """Apply a new password if the token is valid, else raise.

    On success: the user's ``password_hash`` is updated, every active
    session of the user is revoked (mirrors ``change_password``), the
    token row is stamped ``used_at`` so a replay is rejected, and an
    ``auth.password_reset_confirmed`` audit row is written.

    Every failure raises a single ``AuthenticationError`` with code
    ``INVALID_RESET_TOKEN`` — the client cannot tell whether the token
    was missing, expired, or already used.
    """
    if not token:
        raise AuthenticationError(
            code="INVALID_RESET_TOKEN",
            message="The reset link is invalid or has expired.",
        )

    digest = _hash_token(token)
    row = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == digest)
    )
    if row is None or row.used_at is not None or _as_utc(row.expires_at) <= _now():
        raise AuthenticationError(
            code="INVALID_RESET_TOKEN",
            message="The reset link is invalid or has expired.",
        )

    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError(
            code="INVALID_RESET_TOKEN",
            message="The reset link is invalid or has expired.",
        )

    user.password_hash = hash_password(new_password)
    user.updated_at = _now()
    row.used_at = _now()

    # Revoke every active session of the user — same logic as
    # ``services.auth.change_password``.
    stmt = select(Session).where(
        Session.user_id == user.id,
        Session.revoked_at.is_(None),
    )
    sessions = list(await db.scalars(stmt))
    for s in sessions:
        s.revoked_at = _now()
        s.revoked_reason = "password_reset"

    db.add(
        AuditLog(
            action="auth.password_reset_confirmed",
            actor_id=user.id,
            actor_username=user.username,
            target_type="user",
            target_id=str(user.id),
            target_label=user.username,
            payload={"sessions_revoked": len(sessions)},
        )
    )

    logger.info(
        "password_reset_confirmed",
        user_id=str(user.id),
        sessions_revoked=len(sessions),
    )
