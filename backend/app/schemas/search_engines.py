"""Pydantic v2 schemas for search engines."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.website import BuildStatus


# ── Nested collection info embedded in responses ──────────────────────────────

class SearchEngineCollectionItem(BaseModel):
    id: uuid.UUID
    slug: str
    title: str

    model_config = {"from_attributes": True}


# ── CRUD schemas ──────────────────────────────────────────────────────────────

class SearchEngineCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=256)
    xslt_template_id: uuid.UUID | None = None
    collection_ids: list[uuid.UUID] = Field(default_factory=list)


class SearchEngineUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    xslt_template_id: uuid.UUID | None = None
    collection_ids: list[uuid.UUID] | None = None


class SearchEngineResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    xslt_template_id: uuid.UUID | None
    build_status: BuildStatus
    last_build_at: datetime | None
    build_error: str | None
    collections: list[SearchEngineCollectionItem]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Public search result schemas ──────────────────────────────────────────────

class SearchHit(BaseModel):
    collection_slug: str
    filename: str
    title: str | None   # TEI titleStmt/title; null when absent
    doc_url: str        # /browse/{collection_slug}/{filename}
    score: float
    mode: str           # "lucene" | "contains"
    kwic: str           # text snippet


class SearchEngineSearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]
