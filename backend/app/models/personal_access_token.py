"""ORM model for ``personal_access_tokens`` (Phase CLI-A).

A long-lived bearer token issued by an Editor+ from their profile to
authenticate the standalone ``aracne-cli`` against the REST API. The
plaintext value is shown only in the response of the issue endpoint;
``hashed_token`` is a bcrypt digest, so DB exfiltration cannot be used
to log in as the user.

Mirrors the ``mcp_tokens`` shape from migration 0070 / models/corpus.py
but is keyed on ``user_id`` (not ``corpus_id``) and inherits the
issuer's role at request time — no per-token scoping in v1.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class PersonalAccessToken(Base):
    """Long-lived bearer for a single user's CLI access.

    Same auth path as the JWT ``Authorization: Bearer …`` header — the
    middleware in ``app/middleware/acl.py`` detects the
    ``aracne2_pat_`` prefix and routes to ``resolve_pat`` instead of
    ``decode_token``. On match, ``request.state.user`` /
    ``request.state.role`` are populated so every existing
    ``require_role`` guard works unchanged.

    Revocation = stamping ``revoked_at``. Rows are never hard-deleted
    so the audit trail remains intact even after rotation.
    """

    __tablename__ = "personal_access_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    hashed_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
