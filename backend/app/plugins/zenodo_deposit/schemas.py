"""Zenodo deposit — Pydantic schemas for admin config and deposit status."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Zenodo's two known REST endpoints.  Keep these as a Literal so the admin UI
# can render a dropdown instead of a free-text field.
ZenodoBaseUrl = Literal[
    "https://sandbox.zenodo.org",
    "https://zenodo.org",
]

# Record access visibility. Simplified from the legacy four values to two —
# InvenioRDM's "embargoed" requires an ``until`` date and a separate UI
# that we do not ship in the MVP; "closed" is not an InvenioRDM concept.
AccessMode = Literal["open", "restricted"]


class ResourceTypeOption(BaseModel):
    """One entry from the resource-type dropdown, normalised for the UI."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    group: str


class ZenodoConfigResponse(BaseModel):
    """Non-sensitive fields surfaced to the admin UI.

    The API token is never returned in plaintext — a boolean ``token_set``
    flag tells the UI whether a token is configured.
    """

    model_config = ConfigDict(extra="forbid")

    token_set: bool
    base_url: str
    default_community: str
    auto_publish: bool
    access: AccessMode
    resource_type: str  # InvenioRDM vocabulary id, e.g. "publication-book"
    public_base_url: str


class ZenodoConfigUpdate(BaseModel):
    """Partial update — every field is optional.

    Passing ``api_token=""`` clears the stored token; omitting the field
    leaves the current value untouched.
    """

    model_config = ConfigDict(extra="forbid")

    api_token: str | None = Field(default=None, max_length=512)
    base_url: ZenodoBaseUrl | None = None
    default_community: str | None = Field(default=None, max_length=128)
    auto_publish: bool | None = None
    access: AccessMode | None = None
    resource_type: str | None = Field(default=None, max_length=128)
    public_base_url: str | None = Field(default=None, max_length=512)

    @field_validator("public_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip().rstrip("/")
        if stripped and not (stripped.startswith("http://") or stripped.startswith("https://")):
            raise ValueError("public_base_url must start with http:// or https://")
        return stripped


class DepositStatus(BaseModel):
    """Read-only snapshot of the most recent deposit for a collection."""

    model_config = ConfigDict(extra="allow")

    deposit_id: str | None = None
    doi: str | None = None
    record_url: str | None = None
    status: Literal["draft", "published", "failed"]
    submitted_at: datetime
    error: str | None = None
