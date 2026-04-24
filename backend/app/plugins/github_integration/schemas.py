"""Github plugin — Pydantic v2 request/response schemas.

Mirrors the non-native-plugin pattern used by other Aracne2 plugins:
every schema opts into ``extra="forbid"`` so typos at the HTTP layer
surface as 422 errors rather than silent drops.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


# ── Config ─────────────────────────────────────────────────────────────────


class GithubConfig(BaseModel):
    """Read model for ``GET /plugins/github/config``.

    Never returns the decrypted PAT; only a boolean ``pat_set`` flag
    so the admin UI can decide whether to render "A key is currently
    configured (hidden)" vs. "No key yet".
    """

    model_config = ConfigDict(extra="forbid")

    pat_set: bool


class GithubConfigUpdate(BaseModel):
    """Write model for ``PUT /plugins/github/config``.

    Sending ``pat=""`` clears the global PAT; ``pat=None`` (field
    omitted) leaves it untouched.
    """

    model_config = ConfigDict(extra="forbid")

    pat: str | None = None


# ── Links ──────────────────────────────────────────────────────────────────


class GithubLinkBase(BaseModel):
    """Shared fields for create/update link payloads."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(
        default="https://github.com",
        min_length=8,
        max_length=256,
        description=(
            "GitHub base URL; defaults to github.com. Set to a "
            "GitHub Enterprise Server root (e.g. https://ghe.example.com) "
            "to target a self-hosted instance — the adapter transparently "
            "rewrites the API calls to the /api/v3/ prefix."
        ),
    )
    repo_owner: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    branch: str = Field(default="main", min_length=1, max_length=128)
    # ``None`` = don't touch existing override; ``""`` = clear it; any
    # other value = new PAT to encrypt.
    pat_override: str | None = None

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("repo_owner", "repo_name")
    @classmethod
    def _slug_like(cls, v: str) -> str:
        v = v.strip()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}",
            )
        return v

    @field_validator("branch")
    @classmethod
    def _branch_shape(cls, v: str) -> str:
        v = v.strip()
        if not _BRANCH_RE.match(v):
            raise ValueError(
                "must match [A-Za-z0-9][A-Za-z0-9._/-]{0,127}",
            )
        return v


class GithubLinkCreate(GithubLinkBase):
    """Body of ``PUT /plugins/github/collections/{slug}/link``."""


class GithubLinkResponse(BaseModel):
    """Read model — safe for anyone with read access to the collection."""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    repo_owner: str
    repo_name: str
    branch: str
    # The PAT itself is never echoed back; only the boolean says
    # whether a per-link override is currently in effect.
    pat_override_set: bool
    last_push_sha: str | None
    last_push_at: datetime | None
    initialized_at: datetime | None
    initialized_from_sha: str | None
    html_url: str
    """Convenience: ``{base_url}/{repo_owner}/{repo_name}``."""


# ── Push ───────────────────────────────────────────────────────────────────


class GithubPushRequest(BaseModel):
    """Body of ``POST /plugins/github/collections/{slug}/push``.

    ``message`` is optional; a sensible default is composed by the
    service when omitted.
    """

    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(default=None, max_length=500)


class GithubPushResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
    committed_at: datetime
    html_url: str | None
    file_count: int


# ── Initialize ─────────────────────────────────────────────────────────────


class GithubInitializeResponse(BaseModel):
    """Shape returned by the one-shot Initialize endpoint."""

    model_config = ConfigDict(extra="forbid")

    file_count: int
    head_sha: str
    initialized_at: datetime


# ── Website links ─────────────────────────────────────────────────────────


class GithubWebsiteLinkCreate(GithubLinkBase):
    """Body of ``PUT /plugins/github/websites/{slug}/link``.

    Same shape as the collection-link create payload — the link table
    is schema-compatible, just scoped to a different entity.
    """


class GithubWebsiteLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    repo_owner: str
    repo_name: str
    branch: str
    pat_override_set: bool
    last_push_sha: str | None
    last_push_at: datetime | None
    last_push_file_count: int | None
    html_url: str


class GithubWebsitePushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(default=None, max_length=500)


class GithubWebsitePushResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
    committed_at: datetime
    html_url: str | None
    file_count: int
