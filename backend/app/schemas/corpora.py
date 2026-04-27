"""Pydantic v2 schemas for corpora and MCP tokens.

A corpus is a thematic grouping of public collections; an MCP token
grants programmatic read access scoped to a single corpus. Both are
Admin-only at the API layer (see ``app/routers/corpora.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Corpus core ───────────────────────────────────────────────────────────────


class CorpusCollectionItem(BaseModel):
    """A collection summary embedded inside a CorpusResponse."""

    id: uuid.UUID
    slug: str
    title: str
    is_public: bool
    status: str

    model_config = ConfigDict(from_attributes=True)


class CorpusBase(BaseModel):
    """Fields common to create + update payloads."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)
    # Pure UUID list — the admin SPA passes collection ids; the service
    # writes the corpus_collections rows.
    collection_ids: list[uuid.UUID] = Field(default_factory=list)


class CorpusCreate(CorpusBase):
    pass


class CorpusUpdate(BaseModel):
    """All fields optional — supply only what changes."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2048)
    collection_ids: list[uuid.UUID] | None = None


class CorpusResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    collections: list[CorpusCollectionItem]
    token_count: int

    model_config = ConfigDict(from_attributes=True)


# ── MCP tokens ────────────────────────────────────────────────────────────────


class McpTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)


class McpTokenResponse(BaseModel):
    """Token list-row — never carries the plaintext value."""

    id: uuid.UUID
    label: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class McpTokenCreated(McpTokenResponse):
    """Returned exactly once — at the moment of creation — with the
    plaintext token alongside the metadata. The admin UI shows it,
    then never again.
    """

    plaintext: str
    # Pre-formatted Claude Desktop snippet, keyed off the request's
    # base URL so the admin can copy-paste without manual edits.
    claude_desktop_snippet: str
