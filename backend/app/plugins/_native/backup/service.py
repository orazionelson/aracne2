"""
Backup service — creates ZIP archives of platform data.

Supported scopes
----------------
database    Serialises all PostgreSQL tables to JSON using SQLAlchemy async
            selects. No external pg_dump dependency required.
collections Exports every XML document from every eXist-db collection, one
            file per document, grouped by collection slug.
media       Copies files from settings.media_dir and settings.documents_media_root.

ZIP layout
----------
backup_<timestamp>/
  manifest.json           — metadata (scopes, Aracne2 version, timestamps)
  database/
    <tablename>.json       — array of row dicts, one per table
  collections/
    <slug>/
      <filename>.xml
  media/
    platform/              — settings.media_dir contents (logo, etc.)
    documents/             — settings.documents_media_root contents

Jobs are tracked in an in-memory registry (no DB migration needed). ZIP files
are written to settings.backup_root and served via the /backup/jobs/{id}/download
endpoint. Old ZIP files are cleaned up by a daily APScheduler job that keeps
only the most recent 10 archives.
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog

from app.config import settings
from app.plugins._native.backup.schemas import BackupJobOut, BackupJobStatus, BackupScope

logger = structlog.get_logger()

# ── In-memory job registry ─────────────────────────────────────────────────────

_jobs: dict[UUID, BackupJobOut] = {}


def get_job(job_id: UUID) -> BackupJobOut | None:
    return _jobs.get(job_id)


def list_jobs() -> list[BackupJobOut]:
    return sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)


def delete_job(job_id: UUID) -> bool:
    """Remove a job from the registry and delete its ZIP file if present."""
    job = _jobs.pop(job_id, None)
    if job is None:
        return False
    if job.filename:
        path = settings.backup_root / job.filename
        if path.exists():
            path.unlink(missing_ok=True)
    return True


# ── JSON serialiser for SQLAlchemy row dicts ───────────────────────────────────

def _default(obj: object) -> object:
    """Fallback serialiser for types not handled by json.dumps."""
    import enum
    from uuid import UUID as _UUID

    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _UUID):
        return str(obj)
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


# ── Individual scope exporters ─────────────────────────────────────────────────

async def _export_database(zf: zipfile.ZipFile) -> None:
    """Serialise every mapped SQLAlchemy table to JSON inside the ZIP."""
    from sqlalchemy import inspect, select, text

    from app.db.postgres import AsyncSessionLocal, Base, engine

    async with AsyncSessionLocal() as db:
        # Reflect metadata so we can iterate tables in dependency order.
        async with engine.connect() as conn:
            table_names: list[str] = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )

        for table_name in table_names:
            # Skip Alembic's own version table.
            if table_name == "alembic_version":
                continue
            try:
                rows_result = await db.execute(text(f'SELECT * FROM "{table_name}"'))  # noqa: S608
                keys = list(rows_result.keys())
                rows = [dict(zip(keys, row)) for row in rows_result.fetchall()]
                payload = json.dumps(rows, default=_default, ensure_ascii=False)
                zf.writestr(f"database/{table_name}.json", payload)
                logger.debug("backup_db_table_exported", table=table_name, rows=len(rows))
            except Exception as exc:
                logger.warning("backup_db_table_failed", table=table_name, error=str(exc))


async def _export_collections(zf: zipfile.ZipFile) -> None:
    """Export all XML documents from every eXist-db collection."""
    from sqlalchemy import select

    from app.db.existdb import existdb_client
    from app.db.postgres import AsyncSessionLocal
    from app.models.collection import Collection

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Collection))
        collections = result.scalars().all()

    for col in collections:
        try:
            filenames = await existdb_client.list_collection(col.slug)
        except Exception as exc:
            logger.warning(
                "backup_collection_list_failed", slug=col.slug, error=str(exc)
            )
            continue

        for filename in filenames:
            try:
                xml_bytes = await existdb_client.get_document(col.slug, filename)
                zf.writestr(f"collections/{col.slug}/{filename}", xml_bytes)
            except Exception as exc:
                logger.warning(
                    "backup_document_failed",
                    slug=col.slug,
                    filename=filename,
                    error=str(exc),
                )


def _export_media(zf: zipfile.ZipFile) -> None:
    """Copy platform media files and document media into the ZIP."""
    def _add_dir(src: Path, arc_prefix: str) -> None:
        if not src.exists():
            return
        for file_path in src.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(src)
                zf.write(file_path, f"{arc_prefix}/{rel}")

    _add_dir(settings.media_dir, "media/platform")
    _add_dir(settings.documents_media_root, "media/documents")


# ── Main backup task ───────────────────────────────────────────────────────────

async def _run_backup(job_id: UUID, scopes: list[BackupScope], label: str) -> None:
    """Background task: build the ZIP and update the in-memory job entry."""
    job = _jobs[job_id]
    _jobs[job_id] = BackupJobOut(
        **{**job.model_dump(), "status": BackupJobStatus.RUNNING}
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    zip_filename = f"backup_{timestamp}_{job_id.hex[:8]}.zip"
    zip_path = settings.backup_root / zip_filename

    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                "aracne2_version": "2.0",
                "label": label,
                "scopes": [s.value for s in scopes],
                "created_at": datetime.now(UTC).isoformat(),
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            if BackupScope.DATABASE in scopes:
                await _export_database(zf)
            if BackupScope.COLLECTIONS in scopes:
                await _export_collections(zf)
            if BackupScope.MEDIA in scopes:
                _export_media(zf)

        zip_bytes = buf.getvalue()
        zip_path.write_bytes(zip_bytes)
        size = len(zip_bytes)

        _jobs[job_id] = BackupJobOut(
            **{
                **_jobs[job_id].model_dump(),
                "status": BackupJobStatus.DONE,
                "finished_at": datetime.now(UTC),
                "filename": zip_filename,
                "size_bytes": size,
            }
        )
        logger.info(
            "backup_done",
            job_id=str(job_id),
            filename=zip_filename,
            size_bytes=size,
        )
    except Exception as exc:
        logger.error("backup_failed", job_id=str(job_id), error=str(exc))
        _jobs[job_id] = BackupJobOut(
            **{
                **_jobs[job_id].model_dump(),
                "status": BackupJobStatus.FAILED,
                "finished_at": datetime.now(UTC),
                "error": str(exc),
            }
        )
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)


def start_backup(scopes: list[BackupScope], label: str) -> BackupJobOut:
    """Create a job entry and schedule the background task.

    Returns the initial job object (status=pending) immediately.
    """
    job_id = uuid4()
    now = datetime.now(UTC)
    job = BackupJobOut(
        id=job_id,
        label=label,
        scopes=[s.value for s in scopes],
        status=BackupJobStatus.PENDING,
        started_at=now,
        finished_at=None,
        error=None,
        filename=None,
        size_bytes=None,
    )
    _jobs[job_id] = job
    asyncio.create_task(_run_backup(job_id, scopes, label))
    return job


# ── Cleanup job (called by APScheduler) ───────────────────────────────────────

async def purge_old_backups(keep: int = 10) -> None:
    """Keep the most recent *keep* completed backup ZIPs; delete the rest."""
    done_jobs = sorted(
        [j for j in _jobs.values() if j.status == BackupJobStatus.DONE],
        key=lambda j: j.started_at,
        reverse=True,
    )
    for old_job in done_jobs[keep:]:
        delete_job(old_job.id)
        logger.info("backup_purged", job_id=str(old_job.id))
