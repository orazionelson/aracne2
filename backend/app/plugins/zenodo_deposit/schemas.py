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

# Zenodo access_right values used on deposition metadata.
AccessRight = Literal["open", "embargoed", "restricted", "closed"]

# Zenodo publication_type values.  We keep a short curated subset — editors
# can change it later via the raw setting if needed.
PublicationType = Literal[
    "article",
    "book",
    "section",
    "preprint",
    "thesis",
    "report",
    "other",
]


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
    access_right: AccessRight
    publication_type: PublicationType
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
    access_right: AccessRight | None = None
    publication_type: PublicationType | None = None
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
    """Read-only snapshot of the most recent deposit for a collection.

    Tolerant of the two shapes the plugin writes to ``plugin_data``:
    a successful / draft record carries a ``deposit_id`` and
    ``record_url``; a failed record may carry neither but always carries
    ``status`` and ``submitted_at``.
    """

    model_config = ConfigDict(extra="allow")

    deposit_id: int | None = None
    doi: str | None = None
    record_url: str | None = None
    status: Literal["draft", "published", "failed"]
    submitted_at: datetime
    error: str | None = None
