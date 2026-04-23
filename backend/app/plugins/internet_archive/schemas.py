"""Internet Archive plugin — Pydantic schemas for admin config and status."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InternetArchiveConfigResponse(BaseModel):
    """Non-sensitive fields surfaced to the admin UI.

    Both keys are opaque secrets, never returned in plaintext; two
    booleans tell the UI whether each slot is filled.
    """

    model_config = ConfigDict(extra="forbid")

    access_key_set: bool
    secret_key_set: bool
    auto_archive: bool


class InternetArchiveConfigUpdate(BaseModel):
    """Partial update — every field is optional.

    Passing an empty string for a key clears it.
    """

    model_config = ConfigDict(extra="forbid")

    access_key: str | None = Field(default=None, max_length=256)
    secret_key: str | None = Field(default=None, max_length=256)
    auto_archive: bool | None = None


class ArchiveStatus(BaseModel):
    """Read-only snapshot of the most recent archive attempt for a collection.

    ``status`` mirrors SPN2's lifecycle:

    - ``pending`` — job submitted, no terminal response yet (timed out at
      60s; call ``POST .../refresh`` to re-poll);
    - ``success`` — capture completed, ``wayback_url`` is resolvable;
    - ``failed`` — SPN2 or the network returned an error.
    """

    model_config = ConfigDict(extra="allow")

    job_id: str | None = None
    status: Literal["pending", "success", "failed"]
    original_url: str | None = None
    wayback_url: str | None = None
    timestamp: str | None = None
    submitted_at: datetime
    error: str | None = None
