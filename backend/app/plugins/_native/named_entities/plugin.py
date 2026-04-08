"""
Named Entity Index — native plugin.

Listens to document lifecycle events and maintains a searchable index of
named entities (persons, places, organisations) extracted from TEI markup.

Indexing is triggered automatically on document upload and cleaned up on
document deletion. Admins can trigger a full collection re-index via the
admin API when needed.

Extraction is performed by the XQuery file:
  backend/app/xqueries/named_entities/extract_document.xq

which matches <persName>, <placeName>, <orgName> elements regardless of
whether the document uses the TEI namespace.
"""

import asyncio

import structlog

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.models.collection import Collection
from app.plugins._native.named_entities.router import router

logger = structlog.get_logger()


def _schedule_index(collection: Collection, filename: str) -> None:
    """Fire-and-forget: index one document in a background task."""
    from app.db.existdb import existdb_client
    from app.db.postgres import AsyncSessionLocal
    from app.plugins._native.named_entities.service import index_document

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            try:
                await index_document(db, existdb_client, collection, filename)
                await db.commit()
            except Exception as exc:
                logger.error(
                    "named_entities_background_index_failed",
                    slug=collection.slug,
                    filename=filename,
                    error=str(exc),
                )

    asyncio.create_task(_run())


def _schedule_deindex(collection: Collection, filename: str) -> None:
    """Fire-and-forget: remove occurrences for a deleted document."""
    from app.db.postgres import AsyncSessionLocal
    from app.plugins._native.named_entities.service import deindex_document

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            try:
                await deindex_document(db, collection.id, filename)
                await db.commit()
            except Exception as exc:
                logger.error(
                    "named_entities_background_deindex_failed",
                    slug=collection.slug,
                    filename=filename,
                    error=str(exc),
                )

    asyncio.create_task(_run())


async def _on_document_uploaded(collection: Collection, filename: str, **_: object) -> None:
    _schedule_index(collection, filename)


async def _on_document_deleted(collection: Collection, filename: str, **_: object) -> None:
    _schedule_deindex(collection, filename)


hook_registry.register(HookEvent.ON_DOCUMENT_UPLOADED, _on_document_uploaded)
hook_registry.register(HookEvent.ON_DOCUMENT_DELETED, _on_document_deleted)


class Plugin(PluginBase):
    meta = PluginMeta(
        id="named_entities",
        name="Named Entity Index",
        version="1.0.0",
        native=True,
        description=(
            "Extracts and indexes named entities (persons, places, organisations) "
            "from TEI XML documents. Builds a searchable, authority-linkable index "
            "across all collections. Indexing is automatic on upload/delete."
        ),
        author="Aracne2 Team",
        min_role="Admin",
    )
    router = router
