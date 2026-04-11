"""SQLAlchemy ORM model for the XSLT stylesheet catalog."""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import ForeignKey, JSON, String, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class _TextArray(TypeDecorator[list[str]]):
    """Stores list[str] as PostgreSQL ARRAY(Text) on Postgres, JSON on other dialects.

    Using a TypeDecorator keeps the ORM model portable across databases (including
    the SQLite in-memory engine used in tests) while preserving native ARRAY semantics
    in production.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(sa.Text))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[str] | None, dialect: Dialect) -> Any:
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> list[str]:
        if value is None:
            return []
        return list(value)


class XsltTemplate(Base):
    __tablename__ = "xslt_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # "lxml" for XSLT 1.0; "saxon" reserved for future XSLT 2.0/3.0 support.
    processor: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="lxml"
    )
    tags: Mapped[list[str]] = mapped_column(
        _TextArray(), nullable=False, default=list
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
    )
