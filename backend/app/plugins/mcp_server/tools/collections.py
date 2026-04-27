"""MCP tools that expose collection / document data to an LLM client.

All tools intersect their query with the bearer token's corpus scope
(``ctx.collection_ids``) and the read-only filter ``is_public=True &&
status=published``. A token whose corpus is empty therefore sees an
empty result set everywhere — no error, no leak.

Each tool returns a JSON-serialisable Python value; the JSON-RPC
layer wraps it in the MCP ``content`` envelope.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.db.existdb import existdb_client
from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.plugins.mcp_server.auth import McpAuthContext


def _publishable_filter(stmt, scope: frozenset[uuid.UUID]):
    """Restrict a Collection statement to public + published + in-corpus.

    Centralises the three-way filter so tools can't forget one of them.
    """
    return (
        stmt.where(Collection.is_public.is_(True))
        .where(Collection.status == CollectionStatus.published)
        .where(Collection.id.in_(scope) if scope else Collection.id == uuid.UUID(int=0))
    )


# ── list_collections ──────────────────────────────────────────────────────────


LIST_COLLECTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "default": 30,
            "description": "Maximum number of rows to return.",
        },
        "offset": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": "Zero-based row offset for paging.",
        },
    },
    "additionalProperties": False,
}


async def list_collections(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return basic info for every collection visible to *ctx*."""
    limit = max(1, min(int(args.get("limit", 30)), 200))
    offset = max(0, int(args.get("offset", 0)))

    stmt = _publishable_filter(
        select(Collection).order_by(Collection.title.asc()),
        ctx.collection_ids,
    ).limit(limit).offset(offset)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "slug": c.slug,
            "title": c.title,
            "description": c.description,
            "published_at": c.published_at.isoformat() if c.published_at else None,
        }
        for c in rows
    ]


# ── get_collection ────────────────────────────────────────────────────────────


GET_COLLECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "slug": {"type": "string", "minLength": 1, "maxLength": 128},
    },
    "required": ["slug"],
    "additionalProperties": False,
}


async def get_collection(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any]
) -> dict[str, Any]:
    slug = str(args["slug"]).strip()
    stmt = _publishable_filter(
        select(Collection).where(Collection.slug == slug).options(
            selectinload(Collection.editor),
        ),
        ctx.collection_ids,
    )
    c = await db.scalar(stmt)
    if c is None:
        raise NotFoundError(f"Collection {slug!r} not found in this corpus.")

    # Editor name (display-only): the relationship may be null.
    editor_name: str | None = None
    if c.editor_id:
        editor: User | None = await db.scalar(
            select(User).where(User.id == c.editor_id)
        )
        if editor is not None:
            editor_name = editor.display_name or editor.username

    # Document count via eXist-db; fail-soft if eXist is unreachable.
    try:
        doc_list = await existdb_client.list_collection(slug)
        doc_count = len(doc_list)
    except Exception:
        doc_count = -1  # signals "unknown" without breaking the LLM response

    return {
        "slug": c.slug,
        "title": c.title,
        "description": c.description,
        "license_id": c.license_id,
        "schema_id": c.schema_id,
        "published_at": c.published_at.isoformat() if c.published_at else None,
        "target_date": c.target_date.isoformat() if c.target_date else None,
        "document_count": doc_count,
        "editor_display_name": editor_name,
    }


# ── list_documents ────────────────────────────────────────────────────────────


LIST_DOCUMENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "collection_slug": {"type": "string", "minLength": 1, "maxLength": 128},
        "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
        "offset": {"type": "integer", "minimum": 0, "default": 0},
    },
    "required": ["collection_slug"],
    "additionalProperties": False,
}


async def list_documents(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any]
) -> list[dict[str, Any]]:
    slug = str(args["collection_slug"]).strip()
    limit = max(1, min(int(args.get("limit", 100)), 1000))
    offset = max(0, int(args.get("offset", 0)))

    # Verify the collection is in scope before touching eXist.
    in_scope = await db.scalar(
        _publishable_filter(
            select(Collection.id).where(Collection.slug == slug),
            ctx.collection_ids,
        )
    )
    if in_scope is None:
        raise NotFoundError(f"Collection {slug!r} not found in this corpus.")

    try:
        names = await existdb_client.list_collection(slug)
    except Exception:
        return []

    return [{"filename": n} for n in names[offset : offset + limit]]


# ── get_document_source ───────────────────────────────────────────────────────


GET_DOCUMENT_SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "collection_slug": {"type": "string", "minLength": 1, "maxLength": 128},
        "filename": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "required": ["collection_slug", "filename"],
    "additionalProperties": False,
}


# Hard cap so a 100 MB TEI doesn't drown the LLM context. The truncated
# response carries an explicit hint pointing at list_documents for paging.
_MAX_DOCUMENT_BYTES: int = 2 * 1024 * 1024  # 2 MB


async def get_document_source(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any]
) -> dict[str, Any]:
    from app.services.xmldb import _validate_filename  # path-traversal guard

    slug = str(args["collection_slug"]).strip()
    filename = str(args["filename"]).strip()
    _validate_filename(filename)

    in_scope = await db.scalar(
        _publishable_filter(
            select(Collection.id).where(Collection.slug == slug),
            ctx.collection_ids,
        )
    )
    if in_scope is None:
        raise NotFoundError(f"Collection {slug!r} not found in this corpus.")

    try:
        body = await existdb_client.get_document(slug, filename)
    except Exception as exc:
        raise NotFoundError(f"Document {filename!r} not found.") from exc

    if len(body) > _MAX_DOCUMENT_BYTES:
        return {
            "slug": slug,
            "filename": filename,
            "truncated": True,
            "size_bytes": len(body),
            "content": body[:_MAX_DOCUMENT_BYTES].decode("utf-8", errors="replace"),
            "hint": (
                f"Document exceeds {_MAX_DOCUMENT_BYTES // (1024 * 1024)} MB; "
                "only the first chunk is returned. Re-fetch in pieces if needed."
            ),
        }
    return {
        "slug": slug,
        "filename": filename,
        "truncated": False,
        "size_bytes": len(body),
        "content": body.decode("utf-8", errors="replace"),
    }


# ── tei_to_text ───────────────────────────────────────────────────────────────


TEI_TO_TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "collection_slug": {"type": "string", "minLength": 1, "maxLength": 128},
        "filename": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "required": ["collection_slug", "filename"],
    "additionalProperties": False,
}


async def tei_to_text(
    db: AsyncSession, ctx: McpAuthContext, args: dict[str, Any]
) -> dict[str, Any]:
    """Strip TEI markup and return the body text.

    Useful when the LLM's context budget is tight: a TEI document with
    rich apparatus markup can balloon to 10x its plain-text payload.
    Uses ``defusedxml`` so the parse is XXE-proof and ``etree.tostring``
    with ``method="text"`` to extract the document text content.

    Falls back to a regex-based tag-strip if the document fails to
    parse (some TEI files in the wild have entity references the
    parser can't resolve without a DTD).
    """
    import re

    from defusedxml import ElementTree as DET
    from app.services.xmldb import _validate_filename

    slug = str(args["collection_slug"]).strip()
    filename = str(args["filename"]).strip()
    _validate_filename(filename)

    in_scope = await db.scalar(
        _publishable_filter(
            select(Collection.id).where(Collection.slug == slug),
            ctx.collection_ids,
        )
    )
    if in_scope is None:
        raise NotFoundError(f"Collection {slug!r} not found in this corpus.")
    try:
        body = await existdb_client.get_document(slug, filename)
    except Exception as exc:
        raise NotFoundError(f"Document {filename!r} not found.") from exc

    try:
        root = DET.fromstring(body)
        # itertext walks every text node in document order; we join
        # with single spaces and collapse runs of whitespace so the
        # output is one paragraph-friendly string.
        text = " ".join(
            t.strip() for t in root.itertext() if t and t.strip()
        )
    except Exception:
        # Fallback: brutal tag strip. Loses some structure but keeps
        # the text content so the LLM still has something to chew on.
        decoded = body.decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", decoded)
        text = re.sub(r"\s+", " ", text).strip()

    if len(text.encode("utf-8")) > _MAX_DOCUMENT_BYTES:
        truncated = True
        text = text.encode("utf-8")[:_MAX_DOCUMENT_BYTES].decode(
            "utf-8", errors="replace"
        )
    else:
        truncated = False

    return {
        "slug": slug,
        "filename": filename,
        "truncated": truncated,
        "char_count": len(text),
        "text": text,
    }
