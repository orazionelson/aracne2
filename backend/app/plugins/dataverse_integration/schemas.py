"""Dataverse plugin — Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PublishType = Literal["major", "minor", "updatecurrent"]


class DataverseConfig(BaseModel):
    """Non-sensitive snapshot of plugin config returned to the admin UI."""

    model_config = ConfigDict(extra="forbid")

    token_set: bool
    base_url: str
    default_alias: str
    auto_deposit: bool
    auto_publish: bool
    default_subject: str
    contact_name: str
    contact_email: str
    publish_type: PublishType
    public_base_url: str


class DataverseConfigUpdate(BaseModel):
    """Partial update — every field is optional. ``api_token=""`` clears."""

    model_config = ConfigDict(extra="forbid")

    api_token: str | None = Field(default=None, max_length=512)
    base_url: str | None = Field(default=None, max_length=512)
    default_alias: str | None = Field(default=None, max_length=128)
    auto_deposit: bool | None = None
    auto_publish: bool | None = None
    default_subject: str | None = Field(default=None, max_length=128)
    contact_name: str | None = Field(default=None, max_length=256)
    contact_email: str | None = Field(default=None, max_length=256)
    publish_type: PublishType | None = None

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().rstrip("/")
        if s and not (s.startswith("http://") or s.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return s


class DataverseDepositStatus(BaseModel):
    """Snapshot of the most recent deposit for a collection or website."""

    model_config = ConfigDict(extra="allow")

    persistent_id: str | None = None
    doi: str | None = None
    landing_url: str | None = None
    status: Literal["draft", "published", "failed"]
    submitted_at: datetime
    error: str | None = None


class CollectionDepositRequest(BaseModel):
    """Body of ``POST /plugins/dataverse/collections/{slug}/deposit``."""

    model_config = ConfigDict(extra="forbid")

    # Per-link override for the Dataverse alias. When omitted, the
    # plugin's ``default_alias`` is used.
    alias: str | None = Field(default=None, max_length=128)


class WebsiteDepositRequest(BaseModel):
    """Body of ``POST /plugins/dataverse/websites/{slug}/deposit``."""

    model_config = ConfigDict(extra="forbid")

    upload_as_zip: bool = True
    alias: str | None = Field(default=None, max_length=128)
