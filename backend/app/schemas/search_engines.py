"""Pydantic v2 schemas for search engines."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.website import BuildStatus


# ── Nested collection info embedded in responses ──────────────────────────────

class SearchEngineCollectionItem(BaseModel):
    id: uuid.UUID
    slug: str
    title: str

    model_config = {"from_attributes": True}


# ── Advanced search configuration ─────────────────────────────────────────────

class AdvancedSearchTag(BaseModel):
    """A named entity tag the admin exposes on the advanced search page.

    Example: label="Persona", element="persName"
    """
    label: str = Field(..., min_length=1, max_length=64)
    element: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9._-]*$",
    )


class AdvancedSearchAttributeFilter(BaseModel):
    """An attribute dimension the admin exposes on the advanced search page.

    Example: label="Ruolo", attribute="role"
    """
    label: str = Field(..., min_length=1, max_length=64)
    attribute: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9._-]*$",
    )


class AdvancedSearchConfig(BaseModel):
    named_tags: list[AdvancedSearchTag] = Field(default_factory=list)
    attribute_filters: list[AdvancedSearchAttributeFilter] = Field(default_factory=list)


# ── Embed configuration ───────────────────────────────────────────────────────

class EmbedConfig(BaseModel):
    """Configuration for the embeddable search widget.

    mode: which forms to include in the widget.
    allowed_origins: list of whitelisted HTTP origins (e.g. "https://example.com").
    An empty list means all origins are allowed (open embed).
    """
    mode: Literal["simple", "advanced", "both"] = "simple"
    allowed_origins: list[str] = Field(default_factory=list)

    @field_validator("allowed_origins")
    @classmethod
    def _validate_origins(cls, v: list[str]) -> list[str]:
        for o in v:
            if not (o.startswith("http://") or o.startswith("https://")):
                raise ValueError(
                    f"Invalid origin {o!r}: must start with http:// or https://"
                )
        return v


# ── CRUD schemas ──────────────────────────────────────────────────────────────

_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class SearchEngineCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    xslt_template_id: uuid.UUID | None = None
    collection_ids: list[uuid.UUID] = Field(default_factory=list)
    # 0 = cache disabled; default 60 minutes.
    cache_ttl_minutes: int = Field(default=60, ge=0, le=10080)
    footer_text: str | None = None
    footer_hidden: bool = False
    page_bg_color: str | None = Field(None, pattern=_HEX_COLOR)
    header_bg_color: str | None = Field(None, pattern=_HEX_COLOR)
    header_hidden: bool = False
    custom_css: str | None = None
    custom_js: str | None = None
    include_jquery: bool = False
    advanced_search_enabled: bool = False
    advanced_search_config: AdvancedSearchConfig = Field(
        default_factory=AdvancedSearchConfig
    )
    embed_enabled: bool = False
    embed_config: EmbedConfig = Field(default_factory=EmbedConfig)


class SearchEngineUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    xslt_template_id: uuid.UUID | None = None
    collection_ids: list[uuid.UUID] | None = None
    cache_ttl_minutes: int | None = Field(default=None, ge=0, le=10080)
    footer_text: str | None = None
    footer_hidden: bool | None = None
    page_bg_color: str | None = Field(None, pattern=_HEX_COLOR)
    header_bg_color: str | None = Field(None, pattern=_HEX_COLOR)
    header_hidden: bool | None = None
    custom_css: str | None = None
    custom_js: str | None = None
    include_jquery: bool | None = None
    advanced_search_enabled: bool | None = None
    advanced_search_config: AdvancedSearchConfig | None = None
    embed_enabled: bool | None = None
    embed_config: EmbedConfig | None = None


class SearchEngineResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    xslt_template_id: uuid.UUID | None
    build_status: BuildStatus
    last_build_at: datetime | None
    build_error: str | None
    cache_ttl_minutes: int
    footer_text: str | None
    footer_hidden: bool
    page_bg_color: str | None
    header_bg_color: str | None
    header_hidden: bool
    custom_css: str | None
    custom_js: str | None
    include_jquery: bool
    advanced_search_enabled: bool
    advanced_search_config: AdvancedSearchConfig
    embed_enabled: bool
    embed_config: EmbedConfig
    collections: list[SearchEngineCollectionItem]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    @field_validator("advanced_search_config", mode="before")
    @classmethod
    def _parse_advanced_config(cls, v: object) -> AdvancedSearchConfig:
        if isinstance(v, dict):
            return AdvancedSearchConfig.model_validate(v)
        return v  # type: ignore[return-value]

    @field_validator("embed_config", mode="before")
    @classmethod
    def _parse_embed_config(cls, v: object) -> EmbedConfig:
        if isinstance(v, dict):
            return EmbedConfig.model_validate(v)
        return v  # type: ignore[return-value]

    model_config = {"from_attributes": True}


# ── Embed log entry ───────────────────────────────────────────────────────────

class EmbedLogEntry(BaseModel):
    id: int
    origin: str | None
    referer: str | None
    ip_address: str | None
    query: str
    mode: str
    allowed: bool
    requested_at: datetime

    model_config = {"from_attributes": True}


# ── Public search result schemas ──────────────────────────────────────────────

class SearchHit(BaseModel):
    collection_slug: str
    filename: str
    title: str | None   # TEI titleStmt/title; null when absent
    doc_url: str        # /browse/{collection_slug}/{filename}?highlight=...
    score: float
    mode: str           # "lucene" | "contains" | "advanced-*"
    kwic: str           # text snippet
    element_name: str | None = None  # populated by advanced search


class SearchEngineSearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]
    cached: bool = False  # True when result was served from PostgreSQL cache
