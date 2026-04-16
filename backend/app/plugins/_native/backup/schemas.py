"""Pydantic schemas for the Backup plugin."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class BackupScope(str, Enum):
    DATABASE = "database"
    COLLECTIONS = "collections"
    MEDIA = "media"


class BackupJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class BackupRequest(BaseModel):
    scopes: list[BackupScope] = [
        BackupScope.DATABASE,
        BackupScope.COLLECTIONS,
        BackupScope.MEDIA,
    ]
    label: str = ""


class BackupJobOut(BaseModel):
    id: UUID
    label: str
    scopes: list[str]
    status: BackupJobStatus
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    filename: str | None
    size_bytes: int | None

    model_config = {"from_attributes": True}
