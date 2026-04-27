import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class AiPrompt(Base):
    __tablename__ = "ai_prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Prompt body — use {variable_name} placeholders.
    template: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON array of variable names required in the context dict.
    context_vars: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    # Where the prompt is auto-cabled in the UI. One of:
    #   "editor.selection"   — TEI editor button, input = active selection.
    #   "editor.document"    — TEI editor button, input = whole document.
    #   "editor.validation"  — TEI editor / Collection detail validation panel.
    #   "editor.discuss"     — TEI editor multi-turn chat.
    #   "xslt.debug"         — Website XSLT editor debug button.
    #   "xslt.discuss"       — Website XSLT editor multi-turn chat.
    #   "bibliobuilder"      — Bibliobuilder workflow modality picker.
    #   None                 — orphan: visible only in Settings → AI.
    scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Native prompts are seeded by the platform and cannot be deleted.
    is_native: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="FALSE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
