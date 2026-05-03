"""ORM model for the ``password_reset_tokens`` table (Phase EM-C).

Each row pairs a user with the SHA-256 digest of a one-time recovery
token. ``request_reset`` inserts; ``confirm_reset`` matches by digest
and either applies the new password (and stamps ``used_at``) or rejects
the attempt.

The plaintext token is never stored — see
``backend/alembic/versions/0074_password_reset_tokens.py`` for the
rationale and the table layout.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 hex digest of the plaintext token (64 chars). Never stores
    # the raw token — exfiltration of this table cannot be used to reset
    # accounts.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Stamped on first successful confirm. After that the row is
    # rejected on every further confirm attempt — single-use enforced.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
