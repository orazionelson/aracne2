"""Pydantic schemas for the document_versions REST API (Phase C).

Read schemas omit ``xml_content`` — the compressed body is fetched on demand
via the dedicated ``/{n}/content`` endpoint so listing the history of a
document does not stream gzipped blobs the editor never asked for.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.document_version import VersionOrigin


class DocumentVersionResponse(BaseModel):
    """Metadata-only view of a ``document_versions`` row."""

    id: uuid.UUID
    collection_id: uuid.UUID
    document_filename: str
    version_number: int
    content_sha256: str
    size_bytes: int
    origin: VersionOrigin
    message: str | None
    created_at: datetime
    created_by_id: uuid.UUID | None
    audit_log_id: int | None

    model_config = {"from_attributes": True}


class ManualSaveRequest(BaseModel):
    """Body for ``POST .../versions`` — Editor+ explicit "Save version".

    The message is required so the editor's history reads as a sequence
    of intentional checkpoints rather than opaque timestamps.
    """

    message: str = Field(min_length=1, max_length=2000)


class RollbackRequest(BaseModel):
    """Body for ``POST .../versions/{n}/rollback`` — optional note."""

    note: str | None = Field(default=None, max_length=2000)


class DiffResponse(BaseModel):
    """Unified diff between two versions of the same document.

    The diff is line-based (``difflib.unified_diff``) over the decoded XML
    bodies. Both sides are referenced by their per-(collection, filename)
    monotonic ``version_number``.
    """

    from_version: int
    to_version: int
    diff: str
