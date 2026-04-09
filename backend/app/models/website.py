"""SQLAlchemy ORM models for websites and website pages."""

import uuid
from datetime import UTC, datetime
from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class RenderingMode(str, PyEnum):
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"
    HYBRID = "HYBRID"


class BuildStatus(str, PyEnum):
    idle = "idle"
    pending = "pending"
    building = "building"
    done = "done"
    failed = "failed"


class Website(Base):
    __tablename__ = "websites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rendering_mode: Mapped[RenderingMode] = mapped_column(
        sa.Enum(RenderingMode, name="website_rendering_mode", create_type=False),
        nullable=False,
        default=RenderingMode.STATIC,
    )
    theme_config: Mapped[dict] = mapped_column(
        JSONB(), nullable=False, default=dict
    )
    # HTML and Dublin Core <meta> tags for every generated page
    meta_config: Mapped[dict] = mapped_column(
        JSONB(), nullable=False, default=dict
    )
    nav_config: Mapped[list] = mapped_column(
        JSONB(), nullable=False, default=list
    )
    xslt_schema_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tei_schemas.id", ondelete="SET NULL"),
        nullable=True,
    )
    build_status: Mapped[BuildStatus] = mapped_column(
        sa.Enum(BuildStatus, name="website_build_status", create_type=False),
        nullable=False,
        default=BuildStatus.idle,
    )
    last_build_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    build_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_published: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    pages: Mapped[list["WebsitePage"]] = relationship(
        "WebsitePage",
        back_populates="website",
        cascade="all, delete-orphan",
        order_by="WebsitePage.sort_order",
    )


class WebsitePage(Base):
    __tablename__ = "website_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    website_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content_md: Mapped[str | None] = mapped_column(Text(), nullable=True)
    sort_order: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0)
    is_hidden: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    website: Mapped["Website"] = relationship("Website", back_populates="pages")
