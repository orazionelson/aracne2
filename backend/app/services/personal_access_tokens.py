"""Service layer for ``personal_access_tokens`` (Phase CLI-A).

Long-lived bearer tokens an Editor+ issues from their Profile to
authenticate the standalone ``aracne-cli`` against the REST API. The
plaintext value is shown only in the response of the issue endpoint;
the DB stores the bcrypt digest, mirroring the ``mcp_tokens`` pattern
in ``services/corpora.py``.

Public API:

- ``issue_pat(db, user, label) -> tuple[PersonalAccessToken, str]``:
  generates plaintext + stores bcrypt digest. Returns the row + the
  plaintext, the only moment it's visible.
- ``list_pats(db, user)``: every non-revoked row of *user*, newest first.
- ``revoke_pat(db, user, token_id)``: stamps ``revoked_at``; idempotent.
- ``resolve_pat(db, plaintext) -> User | None``: detects the prefix,
  walks every non-revoked row, bcrypt-checks, bumps ``last_used_at``
  on match.

Token format: ``aracne2_pat_`` + ``secrets.token_urlsafe(32)`` (43 chars
of url-safe base64 → 32 bytes of randomness, well above the practical
lower bound for bearer tokens).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.core.password import hash_password, verify_password
from app.models.personal_access_token import PersonalAccessToken
from app.models.user import User

logger = structlog.get_logger()

#: Self-identifying prefix on every issued plaintext. The auth
#: middleware uses it to dispatch to ``resolve_pat`` instead of the
#: JWT decode path.
PAT_PREFIX: Final[str] = "aracne2_pat_"


def _now() -> datetime:
    return datetime.now(UTC)


async def issue_pat(
    db: AsyncSession, *, user: User, label: str
) -> tuple[PersonalAccessToken, str]:
    """Generate a new PAT for *user*.

    Returns ``(row, plaintext)``. The plaintext is the only place where
    the token value is visible — after this call it's gone from the
    backend forever (the DB stores only the bcrypt digest).
    """
    label = label.strip()
    if not label:
        raise DomainValidationError(
            "INVALID_LABEL", "Token label cannot be empty."
        )

    plaintext = PAT_PREFIX + secrets.token_urlsafe(32)
    row = PersonalAccessToken(
        user_id=user.id,
        label=label,
        hashed_token=hash_password(plaintext),
    )
    db.add(row)
    await db.flush()
    logger.info(
        "personal_access_token_issued",
        user_id=str(user.id),
        token_id=str(row.id),
    )
    return row, plaintext


async def list_pats(
    db: AsyncSession, user: User
) -> list[PersonalAccessToken]:
    """Return every non-revoked PAT belonging to *user*, newest first."""
    rows = await db.execute(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user.id)
        .where(PersonalAccessToken.revoked_at.is_(None))
        .order_by(PersonalAccessToken.created_at.desc())
    )
    return list(rows.scalars().all())


async def revoke_pat(
    db: AsyncSession, *, user: User, token_id: uuid.UUID
) -> None:
    """Stamp ``revoked_at``. Idempotent — already-revoked rows stay so.

    Raises ``NotFoundError`` when the row does not belong to *user*
    (or does not exist) so an editor cannot revoke another user's
    tokens by guessing IDs.
    """
    row = await db.scalar(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.id == token_id)
        .where(PersonalAccessToken.user_id == user.id)
    )
    if row is None:
        raise NotFoundError(f"Personal access token {token_id} not found.")
    if row.revoked_at is None:
        row.revoked_at = _now()
        await db.flush()
        logger.info(
            "personal_access_token_revoked",
            user_id=str(user.id),
            token_id=str(token_id),
        )


async def resolve_pat(
    db: AsyncSession, plaintext: str
) -> User | None:
    """Look up the user for *plaintext*, or None.

    Bearers that don't carry the ``aracne2_pat_`` prefix are rejected
    without touching the DB so the auth middleware can fast-path a
    non-PAT token (typically a JWT) to its own decode path.

    For matching bearers we walk every non-revoked row and
    ``verify_password`` — bcrypt is intentionally slow, but the row
    count is bounded (one editor rarely issues more than a handful of
    PATs) and an attacker without a matching prefix never reaches this
    loop. Same trade-off ``services/corpora.py:resolve_token`` makes.

    Side effect: bumps ``last_used_at`` on the matched row.
    """
    if not plaintext.startswith(PAT_PREFIX):
        return None
    rows = (
        await db.execute(
            select(PersonalAccessToken).where(
                PersonalAccessToken.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    for row in rows:
        if verify_password(plaintext, row.hashed_token):
            row.last_used_at = _now()
            await db.flush()
            user = await db.get(User, row.user_id)
            if user is None or not user.is_active:
                return None
            return user
    return None
