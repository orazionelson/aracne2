import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), default=None)
    preferred_lang: Mapped[str] = mapped_column(String(5), nullable=False, default="it")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Workflow-email opt-out. Default ``True`` so freshly migrated rows
    # keep receiving submitted/rejected/published notifications.
    # Transactional emails (password reset) bypass this toggle.
    email_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="TRUE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Canonical ORCID identifier in the XXXX-XXXX-XXXX-XXXX form (the final
    # character may be X as checksum). Null = user has no ORCID on file.
    # Flows through to Zenodo creator.identifiers and LOD schema:sameAs when
    # this user is the editor of a deposited / published collection.
    orcid: Mapped[str | None] = mapped_column(String(19), default=None)
    # Filename suffix of the uploaded avatar — when set, the file lives at
    # ``settings.media_dir / "avatars" / <user_id>.<ext>`` and is served via
    # ``GET /api/v1/users/{username}/avatar``. None means "no upload, fall
    # back to a deterministic monogram in the UI".
    avatar_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Short freeform bio shown on the in-app Profile page. A tiny Markdown
    # subset is allowed (``**bold**``, ``*italic*``, ``__underline__``);
    # rendering is the frontend's job. Max 500 characters enforced at the
    # API schema layer.
    bio: Mapped[str | None] = mapped_column(Text, default=None)

    user_roles: Mapped[list["UserRole"]] = relationship(  # type: ignore[name-defined]
        "UserRole",
        foreign_keys="UserRole.user_id",
        back_populates="user",
    )
    sessions: Mapped[list["Session"]] = relationship(  # type: ignore[name-defined]
        "Session", back_populates="user"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # type: ignore[name-defined]
        "AuditLog",
        foreign_keys="AuditLog.actor_id",
        back_populates="actor",
    )
