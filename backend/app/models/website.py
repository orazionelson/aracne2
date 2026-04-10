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
    # XSLT configuration for document rendering during static build.
    # Keys: source ("default"|"custom"|"url"), content (str|null),
    #       url (str|null), processor ("lxml"|"saxon").
    xslt_config: Mapped[dict] = mapped_column(
        JSONB(), nullable=False, default=dict
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

    # Tag-discovery cache: {"persName": ["key", "role"], "placeName": ["ref"]}
    distinct_tags: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    tags_refreshed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    pages: Mapped[list["WebsitePage"]] = relationship(
        "WebsitePage",
        back_populates="website",
        cascade="all, delete-orphan",
        order_by="WebsitePage.sort_order",
    )
    indices: Mapped[list["WebsiteIndex"]] = relationship(
        "WebsiteIndex",
        back_populates="website",
        cascade="all, delete-orphan",
        order_by="WebsiteIndex.created_at",
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


class WebsiteIndex(Base):
    """A named index built from a specific XML tag across the website's collection."""

    __tablename__ = "website_indices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    website_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    # XML element local-name to index (e.g. "persName")
    tag: Mapped[str] = mapped_column(String(128), nullable=False)
    # Attribute whose value groups multiple text forms under one key.
    # When null, the element's text content is used as the key directly.
    key_attribute: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Optional further sub-grouping attribute (e.g. "role").
    subkey_attribute: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Pre-built index data, populated by rebuild_website_index().
    cached_data: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    last_built_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
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

    website: Mapped["Website"] = relationship("Website", back_populates="indices")
