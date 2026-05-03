"""Pydantic schemas for the /admin/fixity surface (CTS R7)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.fixity_record import FixityStatus


class FixityRecordView(BaseModel):
    """One row of the fixity table as the admin UI sees it."""

    id: UUID
    collection_id: UUID
    document_filename: str
    expected_sha256: str
    last_seen_sha256: str | None
    version_number: int
    size_bytes: int
    status: FixityStatus
    first_recorded_at: datetime
    last_checked_at: datetime | None
    drifted_at: datetime | None

    model_config = {"from_attributes": True}


class FixitySummary(BaseModel):
    """Per-status row counts for the dashboard cards."""

    ok: int = 0
    drifted: int = 0
    missing: int = 0
    error: int = 0


class FixityRecheckResult(BaseModel):
    """Result of an admin-triggered ``recheck-now``."""

    ok: int = 0
    drifted: int = 0
    missing: int = 0
    error: int = 0
    total: int = 0
