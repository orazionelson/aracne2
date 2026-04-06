import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_jti: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    refresh_jti: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True, default=None
    )
    ip_address: Mapped[str | None] = mapped_column(INET, default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    issued_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    access_expires: Mapped[datetime] = mapped_column(nullable=False)
    refresh_expires: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), default=None)

    user: Mapped["User"] = relationship("User", back_populates="sessions")  # type: ignore[name-defined]
