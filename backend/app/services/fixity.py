"""Fixity layer — CTS R7 deliverable for Milestone 2.

Three responsibilities:

1. :func:`record_publication` — called from ``services.xmldb`` after
   a publication snapshot is committed. Upserts the
   ``fixity_records`` row for the given (collection, filename) pair
   with the SHA-256 / version / size of the latest publication.
2. :func:`recheck_one` — re-hash the row's expected version and
   compare. Stamps ``last_checked_at``, transitions ``status``, and
   sets ``drifted_at`` on the first transition into a drift state.
3. :func:`recheck_all` — sweep every row. Called by the scheduler;
   also exposed as a sync-now Admin endpoint.

Drift is **record-only** by design (per Q7 of the M2 brainstorm):
the platform never auto-quarantines a public render on a hash
mismatch. Surfaces are an audit_log row + the /admin/fixity view.

Scope: the latest ``publication``-origin row of every published
document (Q8 decision). Cheaper to re-check on a schedule than
walking every ``document_versions`` row, and what the public
actually serves.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.collection import Collection
from app.models.document_version import DocumentVersion, VersionOrigin
from app.models.fixity_record import FixityRecord, FixityStatus

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


# ── Recording at deposit time ─────────────────────────────────────────────────


async def record_publication(
    db: AsyncSession,
    *,
    collection: Collection,
    filename: str,
    expected_sha256: str,
    version_number: int,
    size_bytes: int,
) -> FixityRecord:
    """Upsert the fixity row for the latest publication of *filename*.

    Called from the publication path after a ``publication``-origin
    row lands in ``document_versions``. ``expected_sha256`` is the
    digest of the *uncompressed* body (matches
    ``document_versions.content_sha256``).

    On a re-publication the existing row is updated in place — the
    drift counter resets to ``ok`` and the new hash becomes the
    canonical expected value.
    """
    existing = await db.scalar(
        select(FixityRecord).where(
            FixityRecord.collection_id == collection.id,
            FixityRecord.document_filename == filename,
        )
    )
    if existing is None:
        row = FixityRecord(
            collection_id=collection.id,
            document_filename=filename,
            expected_sha256=expected_sha256,
            last_seen_sha256=expected_sha256,
            version_number=version_number,
            size_bytes=size_bytes,
            status=FixityStatus.ok,
            last_checked_at=_now(),
        )
        db.add(row)
        await db.flush()
        logger.info(
            "fixity_record_created",
            collection_id=str(collection.id),
            filename=filename,
            sha256=expected_sha256,
        )
        return row

    existing.expected_sha256 = expected_sha256
    existing.last_seen_sha256 = expected_sha256
    existing.version_number = version_number
    existing.size_bytes = size_bytes
    existing.status = FixityStatus.ok
    existing.drifted_at = None
    existing.last_checked_at = _now()
    await db.flush()
    logger.info(
        "fixity_record_refreshed",
        collection_id=str(collection.id),
        filename=filename,
        sha256=expected_sha256,
    )
    return existing


# ── Re-check job ──────────────────────────────────────────────────────────────


async def recheck_one(
    db: AsyncSession, *, record: FixityRecord
) -> FixityRecord:
    """Re-hash the row's expected version and update the row.

    Reads the gzipped body straight from ``document_versions`` —
    the hash table itself is the source of truth. We do NOT walk
    eXist-db on the re-check path: a discrepancy between the
    eXist-db tree and the ``document_versions`` blob is its own
    separate drift signal that the M2 fixity layer does not
    address (would need a second table — flagged for Milestone 3
    or beyond).

    Status transitions:

    - ``ok`` if the recomputed hash equals ``expected_sha256``;
    - ``drifted`` if it differs;
    - ``missing`` if the version row is gone (e.g. unpublish);
    - ``error`` if the body is unreadable (caller-side gunzip).
    """
    import gzip

    version_row = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.collection_id == record.collection_id,
            DocumentVersion.document_filename == record.document_filename,
            DocumentVersion.version_number == record.version_number,
        )
    )
    now = _now()
    if version_row is None:
        return await _transition(
            db,
            record=record,
            new_status=FixityStatus.missing,
            last_seen=None,
            checked_at=now,
        )

    try:
        body = gzip.decompress(version_row.xml_content)
        actual = _sha256(body)
    except Exception as exc:  # noqa: BLE001 — surface the failure as ``error``
        logger.error(
            "fixity_recheck_unreadable",
            collection_id=str(record.collection_id),
            filename=record.document_filename,
            error=str(exc),
        )
        return await _transition(
            db,
            record=record,
            new_status=FixityStatus.error,
            last_seen=None,
            checked_at=now,
        )

    if actual == record.expected_sha256:
        return await _transition(
            db,
            record=record,
            new_status=FixityStatus.ok,
            last_seen=actual,
            checked_at=now,
        )
    return await _transition(
        db,
        record=record,
        new_status=FixityStatus.drifted,
        last_seen=actual,
        checked_at=now,
    )


async def _transition(
    db: AsyncSession,
    *,
    record: FixityRecord,
    new_status: FixityStatus,
    last_seen: str | None,
    checked_at: datetime,
) -> FixityRecord:
    """Move *record* into *new_status*; emit an audit row on first drift.

    A row that transitions ``ok → drifted`` (or ``ok → missing``)
    stamps ``drifted_at`` and writes an ``audit_log`` row tagged
    ``fixity.drift_detected`` so the operator's audit-log view
    surfaces it. Subsequent re-checks while still drifted do not
    spam the audit log.
    """
    previous = record.status
    record.last_seen_sha256 = last_seen
    record.last_checked_at = checked_at
    record.status = new_status

    just_drifted = (
        previous == FixityStatus.ok
        and new_status in (FixityStatus.drifted, FixityStatus.missing)
    )
    if just_drifted:
        record.drifted_at = checked_at
        db.add(
            AuditLog(
                action="fixity.drift_detected",
                target_type="fixity_record",
                target_id=str(record.id),
                target_label=record.document_filename,
                payload={
                    "collection_id": str(record.collection_id),
                    "filename": record.document_filename,
                    "expected_sha256": record.expected_sha256,
                    "last_seen_sha256": last_seen,
                    "new_status": new_status.value,
                    "version_number": record.version_number,
                },
            )
        )
        logger.warning(
            "fixity_drift_detected",
            collection_id=str(record.collection_id),
            filename=record.document_filename,
            expected=record.expected_sha256,
            actual=last_seen,
            status=new_status.value,
        )
    elif new_status == FixityStatus.ok and previous != FixityStatus.ok:
        # The drift cleared (e.g. operator fixed the row). Reset the
        # drifted_at timestamp so the row no longer looks suspect.
        record.drifted_at = None

    await db.flush()
    return record


async def recheck_all(db: AsyncSession) -> dict[str, int]:
    """Re-check every fixity row. Returns a per-status tally.

    Designed to be called both by the scheduler and the Admin
    "recheck now" button. Streams in chunks of 200 so a multi-
    thousand-row deployment doesn't load the whole table into
    memory at once.
    """
    tally: dict[str, int] = {s.value: 0 for s in FixityStatus}
    last_id: uuid.UUID | None = None
    chunk_size = 200
    while True:
        stmt = select(FixityRecord).order_by(FixityRecord.id).limit(chunk_size)
        if last_id is not None:
            stmt = stmt.where(FixityRecord.id > last_id)
        rows = list(await db.scalars(stmt))
        if not rows:
            break
        for row in rows:
            await recheck_one(db, record=row)
            tally[row.status.value] += 1
        last_id = rows[-1].id
        if len(rows) < chunk_size:
            break
    await db.commit()
    logger.info("fixity_recheck_all_done", **tally)
    return tally


# ── Read paths ────────────────────────────────────────────────────────────────


async def list_records(
    db: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 50,
    status: FixityStatus | None = None,
    collection_id: uuid.UUID | None = None,
) -> tuple[Sequence[FixityRecord], int]:
    """Paginated listing for the /admin/fixity view.

    Default sort puts drift signals first (drifted, missing, error,
    then ok) so the admin lands directly on what needs attention.
    """
    page = max(1, int(page))
    per_page = max(1, min(200, int(per_page)))
    base = select(FixityRecord)
    count_stmt = select(func.count()).select_from(FixityRecord)
    if status is not None:
        base = base.where(FixityRecord.status == status)
        count_stmt = count_stmt.where(FixityRecord.status == status)
    if collection_id is not None:
        base = base.where(FixityRecord.collection_id == collection_id)
        count_stmt = count_stmt.where(FixityRecord.collection_id == collection_id)
    total = int(await db.scalar(count_stmt) or 0)

    # Sort: status priority (drift first), then most-recent check first.
    # ``case`` is the top-level SQLAlchemy construct, NOT a member of
    # ``func`` (``func.case`` builds a fictitious DB function and explodes
    # at runtime with ``unexpected keyword argument 'else_'``).
    status_priority = case(
        (FixityRecord.status == FixityStatus.drifted, 0),
        (FixityRecord.status == FixityStatus.missing, 1),
        (FixityRecord.status == FixityStatus.error, 2),
        (FixityRecord.status == FixityStatus.ok, 3),
        else_=4,
    )
    rows_stmt = (
        base.order_by(status_priority, desc(FixityRecord.last_checked_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = list(await db.scalars(rows_stmt))
    return rows, total


async def status_summary(db: AsyncSession) -> dict[str, int]:
    """Per-status row counts — drives the admin dashboard cards."""
    rows = list(
        await db.execute(
            select(FixityRecord.status, func.count()).group_by(FixityRecord.status)
        )
    )
    out: dict[str, int] = {s.value: 0 for s in FixityStatus}
    for status, count in rows:
        if isinstance(status, FixityStatus):
            out[status.value] = int(count)
        else:
            out[str(status)] = int(count)
    return out


__all__ = [
    "record_publication",
    "recheck_one",
    "recheck_all",
    "list_records",
    "status_summary",
]
