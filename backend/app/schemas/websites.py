"""Pydantic v2 schemas for websites, website pages, and website indices."""

import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.models.website import BuildStatus, RenderingMode


# ── Website pages ─────────────────────────────────────────────────────────────

class WebsitePageCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    content_md: str | None = None
    sort_order: int = 0
    is_hidden: bool = False


class WebsitePageUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    content_md: str | None = None
    sort_order: int | None = None
    is_hidden: bool | None = None


class WebsitePageResponse(BaseModel):
    id: uuid.UUID
    website_id: uuid.UUID
    slug: str
    title: str
    content_md: str | None
    sort_order: int
    is_hidden: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Websites ──────────────────────────────────────────────────────────────────

def _validate_url_scheme(v: str | None) -> str | None:
    """Reject non-http/https schemes to prevent javascript: stored XSS."""
    if not v:
        return v
    v = v.strip()
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("website_url must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("website_url must include a valid hostname")
    return v


class WebsiteCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    collection_id: uuid.UUID | None = None
    rendering_mode: RenderingMode = RenderingMode.STATIC
    website_url: str | None = Field(None, max_length=512)
    theme_config: dict = Field(default_factory=dict)
    meta_config: dict = Field(default_factory=dict)
    nav_config: list = Field(default_factory=list)
    xslt_config: dict = Field(default_factory=dict)
    xslt_schema_id: uuid.UUID | None = None
    is_published: bool = False
    show_in_public_home: bool = False
    custom_css: str | None = None
    custom_js: str | None = None
    include_jquery: bool = False
    maintenance_on_unpublish: bool | None = None  # None → set per-mode default in service
    maintenance_message: str | None = Field(None, max_length=1024)
    contact_email: str | None = Field(None, max_length=256)

    @field_validator("website_url", mode="before")
    @classmethod
    def validate_website_url(cls, v: str | None) -> str | None:
        return _validate_url_scheme(v)


class WebsiteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    collection_id: uuid.UUID | None = None
    rendering_mode: RenderingMode | None = None
    website_url: str | None = Field(None, max_length=512)

    @field_validator("website_url", mode="before")
    @classmethod
    def validate_website_url(cls, v: str | None) -> str | None:
        return _validate_url_scheme(v)
    theme_config: dict | None = None
    meta_config: dict | None = None
    nav_config: list | None = None
    xslt_config: dict | None = None
    xslt_schema_id: uuid.UUID | None = None
    is_published: bool | None = None
    show_in_public_home: bool | None = None
    custom_css: str | None = None
    custom_js: str | None = None
    include_jquery: bool | None = None
    maintenance_on_unpublish: bool | None = None
    maintenance_message: str | None = Field(None, max_length=1024)
    contact_email: str | None = Field(None, max_length=256)


# ── Website indices ───────────────────────────────────────────────────────────

class WebsiteIndexCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    tag: str = Field(..., min_length=1, max_length=128)
    key_attribute: str | None = Field(None, max_length=128)
    subkey_attribute: str | None = Field(None, max_length=128)


class WebsiteIndexUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str | None = Field(None, min_length=1, max_length=256)
    tag: str | None = Field(None, min_length=1, max_length=128)
    key_attribute: str | None = None
    subkey_attribute: str | None = None


class WebsiteIndexResponse(BaseModel):
    id: uuid.UUID
    website_id: uuid.UUID
    label: str
    title: str
    tag: str
    key_attribute: str | None
    subkey_attribute: str | None
    last_built_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Websites ──────────────────────────────────────────────────────────────────

class WebsiteResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    collection_id: uuid.UUID | None
    rendering_mode: RenderingMode
    website_url: str | None
    theme_config: dict
    meta_config: dict
    nav_config: list
    xslt_config: dict
    xslt_schema_id: uuid.UUID | None
    build_status: BuildStatus
    last_build_at: datetime | None
    build_error: str | None
    is_published: bool
    show_in_public_home: bool
    custom_css: str | None
    custom_js: str | None
    include_jquery: bool
    maintenance_on_unpublish: bool
    maintenance_message: str | None
    contact_email: str | None
    distinct_tags: dict | list | None  # dict when populated, [] when XQuery returned no results
    tags_refreshed_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    pages: list[WebsitePageResponse] = Field(default_factory=list)
    indices: list[WebsiteIndexResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WebsiteBuildResponse(BaseModel):
    """Returned immediately when a build is triggered."""
    slug: str
    build_status: BuildStatus
    message: str


class MetaSuggestionsResponse(BaseModel):
    """Pre-computed meta field suggestions for the edit form."""
    author: list[str] = []
    dc_creator: list[str] = []
    designer: list[str] = []
    copyright: str = ""
    dc_publisher: list[str] = []
    dc_format: str = ""
    dc_identifier: str = ""


# ── XSLT preview ──────────────────────────────────────────────────────────────

class WebsitePreviewDocRequest(BaseModel):
    """Optional XSLT config override for the preview-doc endpoint.

    If xslt_config is omitted or null, the endpoint uses the website's saved
    xslt_config.  Pass a full XsltConfig dict to preview unsaved changes.
    """
    xslt_config: dict | None = None


class WebsitePreviewDocResponse(BaseModel):
    """HTML body returned by the preview-doc endpoint."""
    html: str


# ── Cache management ──────────────────────────────────────────────────────────

class WebsiteCacheClearedResponse(BaseModel):
    """Returned by the clear-cache endpoint."""
    cleared: bool


# ── Tags ──────────────────────────────────────────────────────────────────────

class WebsiteTagsResponse(BaseModel):
    """Distinct-tag map for a website's linked collection.

    distinct_tags may be a dict (element → values map), an empty list
    (XQuery returned no results), or None (no refresh has been run yet).
    """
    distinct_tags: dict | list | None
    tags_refreshed_at: datetime | None
