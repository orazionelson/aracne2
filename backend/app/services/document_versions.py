"""Service layer for the ``document_versions`` table — Phase B of versioning.

Concerns covered here:

- ``create_version``: SHA-256 dedup, gzip compression, monotonic
  per-(collection, filename) version_number, optional FK to the audit_log
  row that originated the snapshot. Returns ``None`` when the working tree
  hash matches the latest existing version for that document — that is the
  "skip-on-unchanged" guard the workflow auto-versioning depends on.
- ``list_versions`` / ``get_version`` / ``get_version_content``: read paths.
- ``get_last_publication``: looks up the most recent ``origin=publication``
  row for a document — the public ``?version=N`` endpoint and the M2 fixity
  scheduler both walk this index.
- ``manual_save``: the Editor+ "Save version" entry point. Enforces the
  per-document soft cap from ``system_settings.document_manual_versions_max``.
- ``rollback_to``: constructive rollback. Copies a target version's content
  back into the working tree and writes a new ``origin=rollback`` row.
- ``acquire_doc_lock``: PG transaction-scoped advisory lock keyed on
  (collection_id, document_filename). Prevents two concurrent writers from
  clobbering each other on the same HEAD now that the published-status edit
  lock is gone (Phase A2).

Plain-function API matches the rest of ``services/`` — no class wrappers.
"""

from __future__ import annotations

import gzip
import hashlib
import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DocumentBusyError,
    ManualVersionsLimitReached,
    NotFoundError,
    VersionNotPublic,
)
from app.db.existdb import ExistDBClient
from app.models.audit_log import AuditLog
from app.models.collection import Collection
from app.models.document_version import DocumentVersion, VersionOrigin
from app.models.system_setting import SystemSetting
from app.models.user import User

logger = structlog.get_logger()


_DEFAULT_MANUAL_VERSIONS_MAX = 50


# ── Helpers ────────────────────────────────────────────────────────────────────


def _sha256(xml_bytes: bytes) -> str:
    """SHA-256 hex digest of the *uncompressed* document body."""
    return hashlib.sha256(xml_bytes).hexdigest()


def _gzip(xml_bytes: bytes) -> bytes:
    """Compress with the same level used by the website search-index helper."""
    return gzip.compress(xml_bytes, compresslevel=9)


def _gunzip(xml_bytes: bytes) -> bytes:
    return gzip.decompress(xml_bytes)


async def acquire_doc_lock(
    db: AsyncSession, collection_id: uuid.UUID, filename: str
) -> None:
    """Acquire a PG transaction-scoped advisory lock for a document.

    Locks are released automatically at COMMIT/ROLLBACK. The key is the
    64-bit hash of ``aracne.doc:{collection_id}:{filename}`` so two writers
    targeting the same document serialise, while writers on different
    documents (or different collections) never block each other.

    Raises ``DocumentBusyError`` (409) if the lock cannot be acquired
    immediately. Routers translate that to ``409 DOCUMENT_BUSY`` and the
    frontend retry / merge UX takes over.

    On non-PostgreSQL backends (the SQLite test runner) the advisory lock
    is a no-op: tests run single-threaded so no race can happen, and SQLite
    has no equivalent primitive. Production always runs on PostgreSQL.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    key = f"aracne.doc:{collection_id}:{filename}"
    got = await db.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": key},
    )
    if not got:
        logger.info(
            "document_lock_busy",
            collection_id=str(collection_id),
            filename=filename,
        )
        raise DocumentBusyError()


async def _next_version_number(
    db: AsyncSession, collection_id: uuid.UUID, filename: str
) -> int:
    current = await db.scalar(
        select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
            DocumentVersion.collection_id == collection_id,
            DocumentVersion.document_filename == filename,
        )
    )
    return int(current or 0) + 1


async def _latest_for_document(
    db: AsyncSession, collection_id: uuid.UUID, filename: str
) -> DocumentVersion | None:
    return await db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.collection_id == collection_id,
            DocumentVersion.document_filename == filename,
        )
        .order_by(desc(DocumentVersion.version_number))
        .limit(1)
    )


async def _manual_versions_count(
    db: AsyncSession, collection_id: uuid.UUID, filename: str
) -> int:
    n = await db.scalar(
        select(func.count(DocumentVersion.id)).where(
            DocumentVersion.collection_id == collection_id,
            DocumentVersion.document_filename == filename,
            DocumentVersion.origin == VersionOrigin.manual,
        )
    )
    return int(n or 0)


async def _manual_versions_max(db: AsyncSession) -> int:
    row = await db.get(SystemSetting, "document_manual_versions_max")
    if row is None or row.value is None:
        return _DEFAULT_MANUAL_VERSIONS_MAX
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return _DEFAULT_MANUAL_VERSIONS_MAX


# ── Public API ────────────────────────────────────────────────────────────────


async def create_version(
    db: AsyncSession,
    *,
    collection: Collection,
    filename: str,
    xml_bytes: bytes,
    origin: VersionOrigin,
    actor: User | None,
    audit_log_row: AuditLog | None = None,
    message: str | None = None,
    skip_dedup: bool = False,
) -> DocumentVersion | None:
    """Stage a new ``document_versions`` row.

    Returns ``None`` when ``skip_dedup`` is False (the default) and the
    SHA-256 of *xml_bytes* matches the latest version already on file —
    workflow auto-events use this to keep the table free of "publish on
    unchanged content" noise. ``rollback`` and ``manual`` callers that need
    to record an event regardless of content equality pass ``skip_dedup=True``.

    The row is staged via ``db.add`` and a ``flush`` is issued so the
    row's ``id`` and ``version_number`` are visible to the caller within
    the same transaction. The caller decides whether to ``commit``.
    """
    digest = _sha256(xml_bytes)
    latest = await _latest_for_document(db, collection.id, filename)
    if (
        latest is not None
        and not skip_dedup
        and latest.content_sha256 == digest
    ):
        return None

    version_number = await _next_version_number(db, collection.id, filename)
    row = DocumentVersion(
        collection_id=collection.id,
        document_filename=filename,
        version_number=version_number,
        xml_content=_gzip(xml_bytes),
        content_sha256=digest,
        size_bytes=len(xml_bytes),
        origin=origin,
        message=message,
        created_by_id=actor.id if actor is not None else None,
        audit_log_id=audit_log_row.id if audit_log_row is not None else None,
    )
    db.add(row)
    await db.flush()
    logger.info(
        "document_version_created",
        collection_id=str(collection.id),
        filename=filename,
        version_number=version_number,
        origin=origin.value,
        size_bytes=len(xml_bytes),
    )
    return row


async def list_versions(
    db: AsyncSession,
    *,
    collection_id: uuid.UUID,
    filename: str,
    origin: VersionOrigin | None = None,
) -> Sequence[DocumentVersion]:
    """Return every version of *filename* in *collection_id*, newest first.

    The optional ``origin`` filter is the index-friendly way to power the
    "show only published states" toggle on the editor's history panel and
    the public ``?version=N`` permalink lookup.
    """
    stmt = (
        select(DocumentVersion)
        .where(
            DocumentVersion.collection_id == collection_id,
            DocumentVersion.document_filename == filename,
        )
        .order_by(desc(DocumentVersion.version_number))
    )
    if origin is not None:
        stmt = stmt.where(DocumentVersion.origin == origin)
    return list(await db.scalars(stmt))


async def get_version(
    db: AsyncSession,
    *,
    collection_id: uuid.UUID,
    filename: str,
    version_number: int,
) -> DocumentVersion:
    row = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.collection_id == collection_id,
            DocumentVersion.document_filename == filename,
            DocumentVersion.version_number == version_number,
        )
    )
    if row is None:
        raise NotFoundError(
            f"Version {version_number} of {filename} not found"
        )
    return row


async def get_version_content(
    db: AsyncSession,
    *,
    collection_id: uuid.UUID,
    filename: str,
    version_number: int,
) -> bytes:
    """Return the *uncompressed* XML body of a stored version."""
    row = await get_version(
        db,
        collection_id=collection_id,
        filename=filename,
        version_number=version_number,
    )
    return _gunzip(row.xml_content)


async def get_public_version(
    db: AsyncSession,
    *,
    collection_id: uuid.UUID,
    filename: str,
    version_number: int,
) -> DocumentVersion:
    """Variant of ``get_version`` that rejects non-publication rows.

    Used by the public ``?version=N`` permalink so a manual save or a
    rollback snapshot can never be served to anonymous visitors. Returns
    404 (via ``NotFoundError``) if the version does not exist, 404 (via
    ``VersionNotPublic``) if it does but is not a ``publication``.
    """
    row = await get_version(
        db,
        collection_id=collection_id,
        filename=filename,
        version_number=version_number,
    )
    if row.origin is not VersionOrigin.publication:
        raise VersionNotPublic()
    return row


async def get_last_publication(
    db: AsyncSession,
    *,
    collection_id: uuid.UUID,
    filename: str,
) -> DocumentVersion | None:
    return await db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.collection_id == collection_id,
            DocumentVersion.document_filename == filename,
            DocumentVersion.origin == VersionOrigin.publication,
        )
        .order_by(desc(DocumentVersion.version_number))
        .limit(1)
    )


async def manual_save(
    db: AsyncSession,
    *,
    collection: Collection,
    filename: str,
    xml_bytes: bytes,
    actor: User,
    audit_log_row: AuditLog | None,
    message: str,
) -> DocumentVersion:
    """Stage an Editor+ "Save version" entry.

    Enforces the soft cap on manual versions per document. ``skip_dedup`` is
    True so the editor always sees a row in their history, even when they
    saved without changing content (otherwise the "Save version" UX would
    feel broken — they pressed the button, they expect a row).
    """
    cap = await _manual_versions_max(db)
    current = await _manual_versions_count(db, collection.id, filename)
    if current >= cap:
        raise ManualVersionsLimitReached(current=current, limit=cap)

    row = await create_version(
        db,
        collection=collection,
        filename=filename,
        xml_bytes=xml_bytes,
        origin=VersionOrigin.manual,
        actor=actor,
        audit_log_row=audit_log_row,
        message=message,
        skip_dedup=True,
    )
    assert row is not None  # skip_dedup=True guarantees a row
    return row


async def rollback_to(
    db: AsyncSession,
    existdb: ExistDBClient,
    *,
    collection: Collection,
    filename: str,
    target_version_number: int,
    actor: User,
    audit_log_row: AuditLog | None,
) -> DocumentVersion:
    """Constructive rollback: copy ``vN``'s content into the working tree
    and write a new ``origin=rollback`` row capturing the same content.

    Never destructive — every prior version stays in the table, the new
    ``rollback`` row is just appended at the next ``version_number``.
    Workflow state of the collection is unchanged; the public continues to
    serve the last ``publication`` snapshot until an EiC explicitly
    re-publishes (Decision 4c from the brainstorming).
    """
    target = await get_version(
        db,
        collection_id=collection.id,
        filename=filename,
        version_number=target_version_number,
    )
    body = _gunzip(target.xml_content)
    await existdb.put_document(collection.slug, filename, body)
    row = await create_version(
        db,
        collection=collection,
        filename=filename,
        xml_bytes=body,
        origin=VersionOrigin.rollback,
        actor=actor,
        audit_log_row=audit_log_row,
        message=f"Restored from version {target_version_number}",
        skip_dedup=True,
    )
    assert row is not None
    return row
