"""
Named Entity Index — core service.

Handles extraction, indexing, deindexing, and querying of named entities
from TEI XML documents stored in eXist-db.

Indexing flow per document:
  1. Run XQuery extract_document.xq → <entities> XML
  2. Parse result with defusedxml
  3. Delete existing EntityOccurrence rows for (collection_id, filename)
  4. Upsert NamedEntity rows (case-insensitive canonical_form + type)
  5. Insert EntityOccurrence rows
  6. Refresh occurrence_count on affected NamedEntity rows
  7. Delete NamedEntity rows with occurrence_count = 0 (orphans)

Entity normalisation:
  - canonical_form = raw text as it appears in the document (first occurrence wins)
  - Lookups are case-insensitive (func.lower comparison)
  - authority_ref = @ref attribute value, only if it contains ":" (URI / prefixed ID)
    Internal document references starting with "#" are ignored.
  - Admins can manually correct canonical_form and assign authority_ref via the API.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import defusedxml.ElementTree as defusedET
import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient
from app.models.collection import Collection, CollectionStatus
from app.plugins._native.named_entities.models import (
    EntityOccurrence,
    NamedEntity,
)
from app.plugins._native.named_entities.schemas import (
    EntityOccurrenceResponse,
    NamedEntityResponse,
)

logger = structlog.get_logger()


def _clean_authority_ref(ref: str) -> str | None:
    """Return ref as authority URI, or None if it's just an internal anchor."""
    ref = ref.strip()
    if not ref:
        return None
    # Skip internal document references (e.g. "#person1")
    if ref.startswith("#"):
        return None
    # Accept anything with a colon: http://, https://, viaf:, geonames:, etc.
    if ":" in ref:
        return ref
    return None


# ── Low-level DB helpers ──────────────────────────────────────────────────────

async def _upsert_entity(
    db: AsyncSession,
    entity_type: str,
    canonical_form: str,
    authority_ref: str | None,
) -> NamedEntity:
    """Return existing entity or create a new one (case-insensitive lookup)."""
    entity = await db.scalar(
        select(NamedEntity).where(
            func.lower(NamedEntity.canonical_form) == canonical_form.lower(),
            NamedEntity.type == entity_type,
        )
    )
    if entity is None:
        entity = NamedEntity(
            type=entity_type,
            canonical_form=canonical_form,
            authority_ref=authority_ref,
        )
        db.add(entity)
        await db.flush()
    elif authority_ref and not entity.authority_ref:
        # Enrich existing entity with authority ref if we now have one
        entity.authority_ref = authority_ref
        entity.updated_at = datetime.now(UTC)
    return entity


async def _refresh_entity_counts(
    db: AsyncSession, entity_ids: list[uuid.UUID]
) -> None:
    """Recompute occurrence_count for the given entity IDs and delete orphans."""
    if not entity_ids:
        return

    # Get current counts in one query
    count_rows = await db.execute(
        select(EntityOccurrence.entity_id, func.count(EntityOccurrence.id).label("cnt"))
        .where(EntityOccurrence.entity_id.in_(entity_ids))
        .group_by(EntityOccurrence.entity_id)
    )
    counts: dict[uuid.UUID, int] = {row.entity_id: row.cnt for row in count_rows}

    now = datetime.now(UTC)
    for eid in entity_ids:
        await db.execute(
            update(NamedEntity)
            .where(NamedEntity.id == eid)
            .values(occurrence_count=counts.get(eid, 0), updated_at=now)
        )

    # Remove entities with no remaining occurrences
    await db.execute(
        delete(NamedEntity).where(
            NamedEntity.id.in_(entity_ids),
            NamedEntity.occurrence_count == 0,
        )
    )


# ── Indexing ──────────────────────────────────────────────────────────────────

async def index_document(
    db: AsyncSession,
    existdb: ExistDBClient,
    col: Collection,
    filename: str,
    tags: str = "persName placeName orgName",
) -> int:
    """Extract and store named entities from one document. Returns count inserted.

    *tags* is a whitespace-separated list of TEI local element names to extract,
    e.g. ``"persName placeName orgName objectName measure"``.

    Does NOT commit — the caller is responsible for the transaction boundary.
    """
    doc_path = f"{existdb.col_path(col.slug)}/{filename}"

    try:
        raw = await existdb.xquery(
            "named_entities/extract_document.xq",
            {"doc_path": doc_path, "tags": tags},
        )
    except Exception:
        logger.warning("named_entities_xquery_failed", slug=col.slug, filename=filename)
        return 0

    try:
        root = defusedET.fromstring(raw)
    except Exception:
        logger.warning("named_entities_parse_failed", slug=col.slug, filename=filename)
        return 0

    # Collect entity IDs previously associated with this document
    old_entity_ids = list(
        await db.scalars(
            select(EntityOccurrence.entity_id).where(
                EntityOccurrence.collection_id == col.id,
                EntityOccurrence.filename == filename,
            ).distinct()
        )
    )

    # Remove stale occurrences
    await db.execute(
        delete(EntityOccurrence).where(
            EntityOccurrence.collection_id == col.id,
            EntityOccurrence.filename == filename,
        )
    )

    new_entity_ids: list[uuid.UUID] = []
    for elem in root:
        tag_name = elem.get("type", "").strip()
        if not tag_name:
            continue

        ref_attr = elem.get("ref", "")
        raw_el = elem.find("raw")
        ctx_el = elem.find("context")
        raw_text = (raw_el.text or "").strip() if raw_el is not None else ""
        context_text = (ctx_el.text or "").strip() if ctx_el is not None else ""

        if not raw_text:
            continue

        authority_ref = _clean_authority_ref(ref_attr)
        entity = await _upsert_entity(db, tag_name, raw_text, authority_ref)
        new_entity_ids.append(entity.id)

        db.add(
            EntityOccurrence(
                entity_id=entity.id,
                collection_id=col.id,
                filename=filename,
                raw_form=raw_text[:512],
                context=context_text[:300] if context_text else None,
            )
        )

    await db.flush()
    await _refresh_entity_counts(db, list(set(old_entity_ids + new_entity_ids)))

    logger.info(
        "named_entities_indexed",
        slug=col.slug,
        filename=filename,
        count=len(new_entity_ids),
    )
    return len(new_entity_ids)


async def deindex_document(
    db: AsyncSession,
    collection_id: uuid.UUID,
    filename: str,
) -> None:
    """Remove all occurrences for a deleted document and refresh counts.

    Does NOT commit — the caller is responsible for the transaction boundary.
    """
    affected_ids = list(
        await db.scalars(
            select(EntityOccurrence.entity_id).where(
                EntityOccurrence.collection_id == collection_id,
                EntityOccurrence.filename == filename,
            ).distinct()
        )
    )
    await db.execute(
        delete(EntityOccurrence).where(
            EntityOccurrence.collection_id == collection_id,
            EntityOccurrence.filename == filename,
        )
    )
    await db.flush()
    await _refresh_entity_counts(db, affected_ids)
    logger.info(
        "named_entities_deindexed",
        collection_id=str(collection_id),
        filename=filename,
    )


async def get_tag_config(db: AsyncSession) -> list[str]:
    """Return the list of TEI tag names to extract, from SystemSetting.

    Falls back to the default three TEI names if the setting is absent or invalid.
    The tag name IS the entity type stored in the DB.
    """
    import json
    from app.models.system_setting import SystemSetting

    row = await db.get(SystemSetting, "entity_index_tags")
    if row and row.value:
        try:
            cfg = json.loads(row.value)
            if isinstance(cfg, list) and all(isinstance(e, str) and e.strip() for e in cfg):
                return cfg
        except (json.JSONDecodeError, TypeError):
            pass
    return ["persName", "placeName", "orgName"]


def _tags_param(config: list[str]) -> str:
    """Convert tag list to a whitespace-separated string for the XQuery."""
    return " ".join(config)


async def reindex_collection(
    db: AsyncSession,
    existdb: ExistDBClient,
    col: Collection,
) -> int:
    """Full re-index of a collection. Wipes existing occurrences and rebuilds.

    Reads the current entity_index_tags SystemSetting to determine which TEI
    elements to extract.  Commits after each document so partial results are
    preserved on failure.  Returns the total number of entity occurrences indexed.
    """
    from app.db.postgres import AsyncSessionLocal

    # Read tag config once for the whole batch
    config = await get_tag_config(db)
    tags = _tags_param(config)

    # Collect entity IDs that currently have occurrences in this collection
    old_entity_ids = list(
        await db.scalars(
            select(EntityOccurrence.entity_id).where(
                EntityOccurrence.collection_id == col.id
            ).distinct()
        )
    )
    await db.execute(
        delete(EntityOccurrence).where(EntityOccurrence.collection_id == col.id)
    )
    await db.flush()
    await _refresh_entity_counts(db, old_entity_ids)
    await db.commit()

    filenames = await existdb.list_collection(col.slug)
    total = 0

    for filename in filenames:
        async with AsyncSessionLocal() as doc_db:
            try:
                count = await index_document(doc_db, existdb, col, filename, tags=tags)
                await doc_db.commit()
                total += count
            except Exception as exc:
                logger.error(
                    "named_entities_reindex_doc_failed",
                    slug=col.slug,
                    filename=filename,
                    error=str(exc),
                )

    logger.info("named_entities_reindexed", slug=col.slug, total_occurrences=total)
    return total


# ── Admin mutations ───────────────────────────────────────────────────────────

async def update_entity(
    db: AsyncSession,
    entity_id: uuid.UUID,
    canonical_form: str | None,
    authority_ref: str | None,
) -> NamedEntity | None:
    entity = await db.get(NamedEntity, entity_id)
    if entity is None:
        return None
    if canonical_form is not None:
        entity.canonical_form = canonical_form
    if authority_ref is not None:
        entity.authority_ref = authority_ref or None
    entity.updated_at = datetime.now(UTC)
    await db.flush()
    return entity


async def merge_entities(
    db: AsyncSession,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> NamedEntity | None:
    """Reassign all occurrences from source to target, then delete source."""
    source = await db.get(NamedEntity, source_id)
    target = await db.get(NamedEntity, target_id)
    if source is None or target is None:
        return None

    await db.execute(
        update(EntityOccurrence)
        .where(EntityOccurrence.entity_id == source_id)
        .values(entity_id=target_id)
    )
    await db.flush()
    await db.delete(source)
    await db.flush()

    # Recompute count for the target
    count = await db.scalar(
        select(func.count(EntityOccurrence.id)).where(
            EntityOccurrence.entity_id == target_id
        )
    )
    target.occurrence_count = count or 0
    target.updated_at = datetime.now(UTC)
    await db.flush()
    return target


async def delete_entity(db: AsyncSession, entity_id: uuid.UUID) -> bool:
    entity = await db.get(NamedEntity, entity_id)
    if entity is None:
        return False
    await db.delete(entity)
    return True


# ── Queries ───────────────────────────────────────────────────────────────────

async def get_public_entities(
    db: AsyncSession,
    entity_type: str | None,
    q: str | None,
    page: int,
    per_page: int,
    collection_slug: str | None = None,
) -> tuple[list[NamedEntity], int]:
    """Return entities that appear in at least one published public collection.

    When *collection_slug* is provided, restrict to entities that have at least
    one occurrence in that specific collection (which must also be published+public).
    """
    occ_filter = [
        Collection.status == CollectionStatus.published,
        Collection.is_public.is_(True),
    ]
    if collection_slug:
        occ_filter.append(Collection.slug == collection_slug)

    public_ids_subq = (
        select(EntityOccurrence.entity_id)
        .join(Collection, EntityOccurrence.collection_id == Collection.id)
        .where(*occ_filter)
        .distinct()
        .subquery()
    )

    base = select(NamedEntity).where(NamedEntity.id.in_(select(public_ids_subq.c.entity_id)))
    if entity_type:
        base = base.where(NamedEntity.type == entity_type)
    if q:
        base = base.where(NamedEntity.canonical_form.ilike(f"%{q}%"))

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    rows = list(
        await db.scalars(
            base.order_by(NamedEntity.occurrence_count.desc(), NamedEntity.canonical_form.asc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    return rows, total


async def get_entity_occurrences(
    db: AsyncSession,
    entity_id: uuid.UUID,
    public_only: bool,
    collection_slug: str | None,
    page: int,
    per_page: int,
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated occurrences for one entity, with collection info joined."""
    stmt = (
        select(
            EntityOccurrence,
            Collection.slug.label("collection_slug"),
            Collection.title.label("collection_title"),
        )
        .join(Collection, EntityOccurrence.collection_id == Collection.id)
        .where(EntityOccurrence.entity_id == entity_id)
    )
    if public_only:
        stmt = stmt.where(
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
    if collection_slug:
        stmt = stmt.where(Collection.slug == collection_slug)

    total = await db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0
    rows_raw = (
        await db.execute(
            stmt.order_by(Collection.slug.asc(), EntityOccurrence.filename.asc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    ).all()

    rows = [
        {
            "id": r.EntityOccurrence.id,
            "entity_id": r.EntityOccurrence.entity_id,
            "collection_id": r.EntityOccurrence.collection_id,
            "collection_slug": r.collection_slug,
            "collection_title": r.collection_title,
            "filename": r.EntityOccurrence.filename,
            "raw_form": r.EntityOccurrence.raw_form,
            "context": r.EntityOccurrence.context,
        }
        for r in rows_raw
    ]
    return rows, total


async def get_admin_entities(
    db: AsyncSession,
    entity_type: str | None,
    q: str | None,
    unlinked_only: bool,
    page: int,
    per_page: int,
) -> tuple[list[NamedEntity], int]:
    """Return all entities (admin view — not filtered by collection visibility)."""
    stmt = select(NamedEntity)
    if entity_type:
        stmt = stmt.where(NamedEntity.type == entity_type)
    if q:
        stmt = stmt.where(NamedEntity.canonical_form.ilike(f"%{q}%"))
    if unlinked_only:
        stmt = stmt.where(NamedEntity.authority_ref.is_(None))

    total = await db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0
    rows = list(
        await db.scalars(
            stmt.order_by(NamedEntity.occurrence_count.desc(), NamedEntity.canonical_form.asc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    return rows, total
