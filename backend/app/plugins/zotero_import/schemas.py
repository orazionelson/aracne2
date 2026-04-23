"""Zotero import — Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


LibraryType = Literal["user", "group"]


class ZoteroConfigResponse(BaseModel):
    """Non-sensitive view of the plugin config."""

    model_config = ConfigDict(extra="forbid")

    api_key_set: bool
    library_type: LibraryType
    library_id: str
    api_base: str


class ZoteroConfigUpdate(BaseModel):
    """Partial update — empty string clears the api_key."""

    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(default=None, max_length=256)
    library_type: LibraryType | None = None
    library_id: str | None = Field(default=None, max_length=32)
    api_base: str | None = Field(default=None, max_length=256)


class ZoteroItemPreview(BaseModel):
    """One Zotero item as shown in the preview modal.

    Carries enough context for the editor to decide without opening
    Zotero, plus the opaque ``key`` used for de-duplication.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    item_type: str
    title: str
    creators: list[str] = []
    year: int | None = None
    doi: str | None = None


class ImportPreview(BaseModel):
    """Diff preview for a collection against the Zotero library."""

    model_config = ConfigDict(extra="forbid")

    new: list[ZoteroItemPreview]
    already_imported: list[ZoteroItemPreview]
    total_fetched: int


class ImportRequest(BaseModel):
    """Body of the commit call — a subset of keys to actually import,
    or ``all_new: true`` to import every key currently flagged as new."""

    model_config = ConfigDict(extra="forbid")

    keys: list[str] | None = None
    all_new: bool = False


class ImportResult(BaseModel):
    """Outcome of a successful import."""

    model_config = ConfigDict(extra="forbid")

    imported: int
    skipped: int
    bibliography_version: int
    imported_at: datetime
