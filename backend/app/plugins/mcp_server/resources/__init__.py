"""Resource resolvers for the MCP plugin.

Four URI schemes:

* ``corpus://<name>`` → markdown manifest of the corpus the bearer
  token belongs to (title + description + member collections). The
  ``<name>`` segment is informational; the resolver always returns
  the corpus encoded in the auth context, so a token can't peek at
  a different corpus by guessing names.
* ``collection://<slug>`` → markdown summary (title + description +
  document count + top entities)
* ``document://<slug>/<filename>`` → raw TEI XML (size-capped, same
  guard as the get_document_source tool)
* ``entity://<uuid>`` → entity name + recent occurrences

Resource discovery (``resources/list``) advertises the templates
plus a single materialised ``corpus://`` URI for the bearer's own
corpus — so the LLM client can find it without a tool call.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.existdb import existdb_client
from app.models.collection import Collection, CollectionStatus
from app.plugins._native.named_entities.models import EntityOccurrence, NamedEntity
from app.plugins.mcp_server.auth import McpAuthContext
from app.plugins.mcp_server.tools.collections import _publishable_filter

_MAX_DOCUMENT_BYTES: int = 2 * 1024 * 1024  # match the tool cap


def list_resource_templates() -> list[dict[str, Any]]:
    """Manifest returned by ``resources/list``."""
    return [
        {
            "uriTemplate": "corpus://{name}",
            "name": "Corpus manifest",
            "description": (
                "Markdown manifest of the bearer's corpus: name, "
                "description, and the list of member collections."
            ),
            "mimeType": "text/markdown",
        },
        {
            "uriTemplate": "collection://{slug}",
            "name": "Collection summary",
            "description": "Markdown summary of one collection (title, description, document count).",
            "mimeType": "text/markdown",
        },
        {
            "uriTemplate": "document://{slug}/{filename}",
            "name": "Document TEI source",
            "description": "Raw TEI XML for one document. Capped at 2 MB.",
            "mimeType": "application/xml",
        },
        {
            "uriTemplate": "entity://{id}",
            "name": "Named entity",
            "description": "Canonical form + recent occurrences for one indexed entity.",
            "mimeType": "text/markdown",
        },
    ]


def list_concrete_resources(ctx) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Materialised resources advertised by ``resources/list``.

    Just the bearer's own ``corpus://`` URI — listing every collection
    or document would defeat the lazy-discovery point.
    """
    return [
        {
            "uri": f"corpus://{ctx.corpus.name}",
            "name": ctx.corpus.name,
            "description": ctx.corpus.description or "",
            "mimeType": "text/markdown",
        }
    ]


async def read_resource(
    db: AsyncSession, ctx: McpAuthContext, uri: str
) -> dict[str, Any]:
    """Resolve *uri* and return an MCP ``contents`` array entry.

    Raises ``NotFoundError`` for unknown schemes / out-of-scope IDs /
    parse failures — the JSON-RPC layer maps that to a -32602 error.
    """
    if uri.startswith("corpus://"):
        return _read_corpus(ctx)
    if uri.startswith("collection://"):
        slug = uri[len("collection://"):]
        return await _read_collection(db, ctx, slug)
    if uri.startswith("document://"):
        rest = uri[len("document://"):]
        if "/" not in rest:
            raise NotFoundError(f"Malformed document URI: {uri}")
        slug, filename = rest.split("/", 1)
        return await _read_document(db, ctx, slug, filename)
    if uri.startswith("entity://"):
        eid = uri[len("entity://"):]
        return await _read_entity(db, ctx, eid)
    raise NotFoundError(f"Unknown resource scheme: {uri}")


def _read_corpus(ctx: McpAuthContext) -> dict[str, Any]:
    """Render the bearer's corpus as a markdown manifest.

    Always returns the corpus encoded in *ctx*, regardless of the
    ``<name>`` segment in the URI — a token can't peek at someone
    else's corpus by guessing names.
    """
    corpus = ctx.corpus
    md = [f"# {corpus.name}"]
    if corpus.description:
        md.extend(["", corpus.description])
    md.extend(["", "## Collections", ""])
    if not corpus.collections:
        md.append("_No collections in this corpus yet._")
    else:
        for c in sorted(corpus.collections, key=lambda x: x.title):
            visible = c.is_public and c.status.value == "published"
            badge = "" if visible else " *(not public/published — currently invisible)*"
            md.append(f"- **{c.title}** — `{c.slug}`{badge}")
    return {
        "uri": f"corpus://{corpus.name}",
        "mimeType": "text/markdown",
        "text": "\n".join(md),
    }


async def _read_collection(
    db: AsyncSession, ctx: McpAuthContext, slug: str
) -> dict[str, Any]:
    c = await db.scalar(
        _publishable_filter(
            select(Collection).where(Collection.slug == slug),
            ctx.collection_ids,
        )
    )
    if c is None:
        raise NotFoundError(f"Collection {slug!r} not found in this corpus.")
    try:
        files = await existdb_client.list_collection(slug)
        doc_count = len(files)
    except Exception:
        doc_count = -1
    md_lines = [f"# {c.title}"]
    if c.description:
        md_lines.extend(["", c.description])
    md_lines.extend(
        [
            "",
            f"- **Slug**: `{c.slug}`",
            f"- **Documents**: {doc_count if doc_count >= 0 else 'unknown'}",
            f"- **Published**: {c.published_at.isoformat() if c.published_at else 'n/a'}",
        ]
    )
    return {
        "uri": f"collection://{slug}",
        "mimeType": "text/markdown",
        "text": "\n".join(md_lines),
    }


async def _read_document(
    db: AsyncSession, ctx: McpAuthContext, slug: str, filename: str
) -> dict[str, Any]:
    from app.services.xmldb import _validate_filename

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
    text = body[:_MAX_DOCUMENT_BYTES].decode("utf-8", errors="replace")
    if len(body) > _MAX_DOCUMENT_BYTES:
        text += f"\n<!-- truncated: original size {len(body)} bytes -->"
    return {
        "uri": f"document://{slug}/{filename}",
        "mimeType": "application/xml",
        "text": text,
    }


async def _read_entity(
    db: AsyncSession, ctx: McpAuthContext, eid: str
) -> dict[str, Any]:
    try:
        entity_id = uuid.UUID(eid)
    except ValueError as exc:
        raise NotFoundError(f"Invalid entity id: {eid}") from exc

    entity = await db.scalar(
        select(NamedEntity).where(NamedEntity.id == entity_id)
    )
    if entity is None:
        raise NotFoundError(f"Entity {eid!r} not found.")

    # Verify the entity has at least one occurrence inside the corpus.
    if not ctx.collection_ids:
        raise NotFoundError(f"Entity {eid!r} not visible in this corpus.")
    in_corpus = await db.scalar(
        select(EntityOccurrence.id)
        .join(Collection, Collection.id == EntityOccurrence.collection_id)
        .where(EntityOccurrence.entity_id == entity.id)
        .where(Collection.id.in_(ctx.collection_ids))
        .limit(1)
    )
    if in_corpus is None:
        raise NotFoundError(f"Entity {eid!r} not visible in this corpus.")

    md = [
        f"# {entity.canonical_form}",
        "",
        f"- **Type**: `{entity.type}`",
        f"- **Authority URI**: {entity.authority_uri or 'n/a'}",
        f"- **Total occurrences**: {entity.occurrence_count}",
    ]
    return {
        "uri": f"entity://{entity_id}",
        "mimeType": "text/markdown",
        "text": "\n".join(md),
    }
