"""MCP tools for the named-entities index.

Both tools are wired through the public-entity service and then
intersected with the bearer's corpus scope: the entity must appear in
at least one collection the corpus owns. Without this extra check a
token holder could discover entities present *only* in collections
outside their corpus, leaking the existence of out-of-scope corpora.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.collection import Collection
from app.plugins._native.named_entities.models import (
    EntityOccurrence,
    NamedEntity,
)
from app.plugins._native.named_entities.service import (
    get_entity_occurrences,
    get_public_entities,
)
from app.plugins.mcp_server.auth import McpAuthContext


# ── search_entities ───────────────────────────────────────────────────────────


SEARCH_ENTITIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "q": {"type": "string", "minLength": 1, "maxLength": 200, "description": "Free-text query."},
        "type": {"type": "string", "maxLength": 64, "description": "Restrict to a TEI tag (persName, placeName, …)."},
        "collection_slug": {"type": "string", "maxLength": 128, "description": "Restrict to a single collection."},
        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30},
    },
    "additionalProperties": False,
}


async def search_entities(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any]
) -> list[dict[str, Any]]:
    q = (args.get("q") or "").strip() or None
    entity_type = (args.get("type") or "").strip() or None
    collection_slug = (args.get("collection_slug") or "").strip() or None
    per_page = max(1, min(int(args.get("limit", 30)), 200))

    rows, _total = await get_public_entities(
        db,
        entity_type=entity_type,
        q=q,
        page=1,
        per_page=per_page,
        collection_slug=collection_slug,
    )
    # Filter to entities that have at least one occurrence inside the corpus.
    if not ctx.collection_ids:
        return []
    out: list[dict[str, Any]] = []
    for entity in rows:
        in_corpus = await db.scalar(
            select(EntityOccurrence.id)
            .join(Collection, Collection.id == EntityOccurrence.collection_id)
            .where(EntityOccurrence.entity_id == entity.id)
            .where(Collection.id.in_(ctx.collection_ids))
            .limit(1)
        )
        if in_corpus is None:
            continue
        out.append(
            {
                "id": str(entity.id),
                "canonical_form": entity.canonical_form,
                "type": entity.type,
                "authority_uri": entity.authority_uri,
                "occurrence_count": entity.occurrence_count,
            }
        )
    return out


# ── find_entity_occurrences ──────────────────────────────────────────────────


FIND_ENTITY_OCCURRENCES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entity_id": {"type": "string", "format": "uuid"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
    },
    "required": ["entity_id"],
    "additionalProperties": False,
}


async def find_entity_occurrences(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any]
) -> list[dict[str, Any]]:
    try:
        entity_id = uuid.UUID(str(args["entity_id"]))
    except (ValueError, KeyError) as exc:
        raise NotFoundError(f"Invalid entity_id: {exc}") from exc
    limit = max(1, min(int(args.get("limit", 50)), 500))

    rows, _total = await get_entity_occurrences(
        db,
        entity_id=entity_id,
        public_only=True,
        collection_slug=None,
        page=1,
        per_page=limit,
    )
    if not ctx.collection_ids:
        return []

    # Re-filter on corpus scope. The service joins collection info into
    # each row; we keep only the rows whose collection id is in scope.
    in_scope_ids = ctx.collection_ids
    out: list[dict[str, Any]] = []
    for row in rows:
        collection_id = row.get("collection_id")
        if collection_id is None:
            continue
        try:
            cid = uuid.UUID(str(collection_id)) if not isinstance(collection_id, uuid.UUID) else collection_id
        except ValueError:
            continue
        if cid not in in_scope_ids:
            continue
        out.append(
            {
                "collection_slug": row.get("collection_slug"),
                "document_filename": row.get("document_filename"),
                "raw_form": row.get("raw_form"),
                "context": row.get("context"),
            }
        )
    return out
