"""Pydantic v2 schemas for websites and website pages."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.website import BuildStatus, RenderingMode


# ── Website pages ─────────────────────────────────────────────────────────────

class WebsitePageCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    content_md: str | None = None
    sort_order: int = 0


class WebsitePageUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    content_md: str | None = None
    sort_order: int | None = None


class WebsitePageResponse(BaseModel):
    id: uuid.UUID
    website_id: uuid.UUID
    slug: str
    title: str
    content_md: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Websites ──────────────────────────────────────────────────────────────────

class WebsiteCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    collection_id: uuid.UUID | None = None
    rendering_mode: RenderingMode = RenderingMode.STATIC
    theme_config: dict = Field(default_factory=dict)
    meta_config: dict = Field(default_factory=dict)
    nav_config: list = Field(default_factory=list)
    xslt_schema_id: uuid.UUID | None = None
    is_published: bool = False


class WebsiteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    collection_id: uuid.UUID | None = None
    rendering_mode: RenderingMode | None = None
    theme_config: dict | None = None
    meta_config: dict | None = None
    nav_config: list | None = None
    xslt_schema_id: uuid.UUID | None = None
    is_published: bool | None = None


class WebsiteResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    collection_id: uuid.UUID | None
    rendering_mode: RenderingMode
    theme_config: dict
    meta_config: dict
    nav_config: list
    xslt_schema_id: uuid.UUID | None
    build_status: BuildStatus
    last_build_at: datetime | None
    build_error: str | None
    is_published: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    pages: list[WebsitePageResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WebsiteBuildResponse(BaseModel):
    """Returned immediately when a build is triggered."""
    slug: str
    build_status: BuildStatus
    message: str
