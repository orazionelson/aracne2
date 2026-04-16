"""REST router for the Backup plugin. All endpoints require Admin role."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.config import settings
from app.core.exceptions import NotFoundError
from app.middleware.acl import require_role
from app.plugins._native.backup.schemas import BackupJobOut, BackupRequest, BackupJobStatus
from app.plugins._native.backup.service import (
    delete_job,
    get_job,
    list_jobs,
    start_backup,
)
from app.schemas.common import DataResponse

router = APIRouter(prefix="/backup", tags=["backup"])

_admin = Depends(require_role("Admin"))


@router.post("/jobs", status_code=202)
async def create_backup(
    body: BackupRequest,
    _: None = _admin,
) -> DataResponse[BackupJobOut]:
    """Trigger a new backup job. Returns immediately; job runs in the background."""
    return DataResponse(data=start_backup(body.scopes, body.label))


@router.get("/jobs")
async def get_jobs(
    _: None = _admin,
) -> DataResponse[list[BackupJobOut]]:
    """List all backup jobs (most recent first)."""
    return DataResponse(data=list_jobs())


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: UUID,
    _: None = _admin,
) -> DataResponse[BackupJobOut]:
    """Get the status of a single backup job."""
    job = get_job(job_id)
    if job is None:
        raise NotFoundError(f"Backup job '{job_id}' not found")
    return DataResponse(data=job)


@router.get("/jobs/{job_id}/download")
async def download_backup(
    job_id: UUID,
    _: None = _admin,
) -> FileResponse:
    """Download the ZIP archive for a completed backup job."""
    job = get_job(job_id)
    if job is None:
        raise NotFoundError(f"Backup job '{job_id}' not found")
    if job.status != BackupJobStatus.DONE or not job.filename:
        raise NotFoundError("Backup archive is not yet available")
    zip_path: Path = settings.backup_root / job.filename
    if not zip_path.exists():
        raise NotFoundError("Backup archive file not found on disk")
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=job.filename,
    )


@router.delete("/jobs/{job_id}", status_code=204)
async def remove_job(
    job_id: UUID,
    _: None = _admin,
) -> None:
    """Delete a backup job and its ZIP archive."""
    if not delete_job(job_id):
        raise NotFoundError(f"Backup job '{job_id}' not found")
