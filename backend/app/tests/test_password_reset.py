"""Tests for the Phase EM-C password recovery flow.

Covers the contract that matters for security:
- ``request_reset`` for an existing user inserts a token row and tries
  to send the email; for a missing user it stays silent and inserts
  nothing — but the HTTP endpoint always returns 204 either way.
- ``confirm_reset`` happy path: applies the new password, marks the
  token used, revokes every active session of the user.
- Every confirm failure mode (missing / expired / used / wrong) raises
  the same ``AuthenticationError(code=INVALID_RESET_TOKEN)``.
- The HTTP endpoints accept the schemas and return 204 on success,
  401 on confirm failure.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.password import hash_password, verify_password
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User
from app.services.password_reset import (
    TOKEN_TTL,
    confirm_reset,
    request_reset,
)


def _digest(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_request_reset_creates_token_for_existing_user(
    db_session: AsyncSession,
    seeded_user: User,
) -> None:
    """A real user gets exactly one token row + the email is attempted."""
    with patch(
        "app.services.password_reset.send_mail", new_callable=AsyncMock
    ) as mock_send:
        await request_reset(db_session, seeded_user.email)

    rows = list(
        await db_session.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == seeded_user.id
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].used_at is None
    # SQLite returns naive datetimes from a DateTime(timezone=True)
    # column; normalise before comparing with a tz-aware ``now``.
    expires = rows[0].expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    assert expires > datetime.now(UTC)
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_reset_for_missing_user_inserts_nothing(
    db_session: AsyncSession,
) -> None:
    """An unknown identifier never hits the DB and never sends an email."""
    with patch(
        "app.services.password_reset.send_mail", new_callable=AsyncMock
    ) as mock_send:
        await request_reset(db_session, "nobody@example.org")

    rows = list(await db_session.scalars(select(PasswordResetToken)))
    assert rows == []
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_request_reset_username_lookup(
    db_session: AsyncSession,
    seeded_user: User,
) -> None:
    """``email_or_username`` matches by username too, not just by email."""
    with patch(
        "app.services.password_reset.send_mail", new_callable=AsyncMock
    ) as mock_send:
        await request_reset(db_session, seeded_user.username)

    rows = list(
        await db_session.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == seeded_user.id
            )
        )
    )
    assert len(rows) == 1
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_reset_happy_path(
    db_session: AsyncSession,
    seeded_user: User,
) -> None:
    plaintext = "correct-horse-battery-staple"
    db_session.add(
        PasswordResetToken(
            user_id=seeded_user.id,
            token_hash=_digest(plaintext),
            expires_at=datetime.now(UTC) + TOKEN_TTL,
        )
    )
    # Seed an active session so we can verify revocation.
    import uuid as _uuid

    db_session.add(
        Session(
            user_id=seeded_user.id,
            access_jti=_uuid.uuid4(),
            refresh_jti=_uuid.uuid4(),
            access_expires=datetime.now(UTC) + timedelta(minutes=15),
            refresh_expires=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db_session.flush()
    old_hash = seeded_user.password_hash

    await confirm_reset(db_session, plaintext, "new-secret-password")

    await db_session.refresh(seeded_user)
    assert seeded_user.password_hash != old_hash
    assert verify_password("new-secret-password", seeded_user.password_hash)

    row = await db_session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == _digest(plaintext)
        )
    )
    assert row is not None
    assert row.used_at is not None

    sessions = list(
        await db_session.scalars(
            select(Session).where(Session.user_id == seeded_user.id)
        )
    )
    assert all(s.revoked_at is not None for s in sessions)
    assert any(s.revoked_reason == "password_reset" for s in sessions)


@pytest.mark.asyncio
async def test_confirm_reset_rejects_unknown_token(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(AuthenticationError) as exc:
        await confirm_reset(db_session, "totally-bogus", "new-secret-password")
    assert exc.value.code == "INVALID_RESET_TOKEN"


@pytest.mark.asyncio
async def test_confirm_reset_rejects_expired_token(
    db_session: AsyncSession,
    seeded_user: User,
) -> None:
    plaintext = "expired-token-12345"
    db_session.add(
        PasswordResetToken(
            user_id=seeded_user.id,
            token_hash=_digest(plaintext),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await db_session.flush()

    with pytest.raises(AuthenticationError) as exc:
        await confirm_reset(db_session, plaintext, "new-secret-password")
    assert exc.value.code == "INVALID_RESET_TOKEN"


@pytest.mark.asyncio
async def test_confirm_reset_rejects_already_used_token(
    db_session: AsyncSession,
    seeded_user: User,
) -> None:
    plaintext = "single-use-only"
    db_session.add(
        PasswordResetToken(
            user_id=seeded_user.id,
            token_hash=_digest(plaintext),
            expires_at=datetime.now(UTC) + TOKEN_TTL,
            used_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await db_session.flush()

    with pytest.raises(AuthenticationError) as exc:
        await confirm_reset(db_session, plaintext, "new-secret-password")
    assert exc.value.code == "INVALID_RESET_TOKEN"


@pytest.mark.asyncio
async def test_confirm_reset_rejects_inactive_user(
    db_session: AsyncSession,
    seeded_user: User,
) -> None:
    plaintext = "inactive-user-token"
    db_session.add(
        PasswordResetToken(
            user_id=seeded_user.id,
            token_hash=_digest(plaintext),
            expires_at=datetime.now(UTC) + TOKEN_TTL,
        )
    )
    seeded_user.is_active = False
    await db_session.flush()

    with pytest.raises(AuthenticationError) as exc:
        await confirm_reset(db_session, plaintext, "new-secret-password")
    assert exc.value.code == "INVALID_RESET_TOKEN"


# ── HTTP-level smoke tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoint_request_returns_204_for_unknown_user(
    client_with_existdb: AsyncClient,
) -> None:
    """Account enumeration is closed at the HTTP layer too."""
    res = await client_with_existdb.post(
        "/api/v1/auth/password/reset/request",
        json={"email_or_username": "nope@example.org"},
    )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_endpoint_request_returns_204_for_known_user(
    client_with_existdb: AsyncClient,
    seeded_user: User,
) -> None:
    with patch(
        "app.services.password_reset.send_mail", new_callable=AsyncMock
    ):
        res = await client_with_existdb.post(
            "/api/v1/auth/password/reset/request",
            json={"email_or_username": seeded_user.email},
        )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_endpoint_confirm_invalid_token_returns_401(
    client_with_existdb: AsyncClient,
) -> None:
    res = await client_with_existdb.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": "not-a-real-token", "new_password": "long-enough-1"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_RESET_TOKEN"


@pytest.mark.asyncio
async def test_endpoint_confirm_short_password_returns_422(
    client_with_existdb: AsyncClient,
) -> None:
    """Pydantic validator rejects passwords shorter than 8 chars."""
    res = await client_with_existdb.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": "x" * 16, "new_password": "short"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_endpoint_confirm_happy_path_returns_204(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_user: User,
) -> None:
    plaintext = "http-flow-token-abcdefg"
    db_session.add(
        PasswordResetToken(
            user_id=seeded_user.id,
            token_hash=_digest(plaintext),
            expires_at=datetime.now(UTC) + TOKEN_TTL,
        )
    )
    await db_session.flush()

    res = await client_with_existdb.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": plaintext, "new_password": "the-new-pwd-9"},
    )
    assert res.status_code == 204

    await db_session.refresh(seeded_user)
    assert verify_password("the-new-pwd-9", seeded_user.password_hash)
