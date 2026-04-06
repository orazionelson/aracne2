import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    actor_username: Mapped[str | None] = mapped_column(String(64), default=None)
    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[str | None] = mapped_column(Text, default=None)
    target_label: Mapped[str | None] = mapped_column(Text, default=None)
    ip_address: Mapped[str | None] = mapped_column(INET, default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    payload: Mapped[dict | None] = mapped_column(JSONB, default=None)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    actor: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User",
        foreign_keys=[actor_id],
        back_populates="audit_logs",
    )
