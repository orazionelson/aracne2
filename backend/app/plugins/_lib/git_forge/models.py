"""Shared data models for git-forge adapters.

These are plain dataclasses (not Pydantic) because they are internal
DTOs used between the plugin service layer and the adapters; the
Pydantic surface lives in each plugin's ``schemas.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RepoRef:
    """Identifies a repo on a forge. ``base_url`` is what distinguishes
    codeberg.org from a self-hosted Forgejo, gitlab.com from a
    self-hosted GitLab, github.com from GHE."""

    base_url: str
    owner: str
    name: str


@dataclass(frozen=True)
class DepositFile:
    """A single file to include in a forge commit.

    Paths are forge-relative (POSIX); content is bytes — adapters
    base64-encode as required by the upstream API.
    """

    path: str
    content: bytes


@dataclass(frozen=True)
class DepositManifest:
    """The full set of files to sync to the forge, plus commit
    metadata. The adapter is expected to produce **a single commit**
    that contains every file in ``files`` (create-or-update semantics)."""

    files: list[DepositFile]
    branch: str
    commit_message: str
    committer_name: str
    committer_email: str


@dataclass(frozen=True)
class CommitResult:
    """What the forge returned after a successful push."""

    sha: str
    committed_at: datetime
    html_url: str | None = None


@dataclass(frozen=True)
class TreeEntry:
    """One item returned by ``list_tree`` during Initialize."""

    path: str
    sha: str
    size: int | None = None


@dataclass(frozen=True)
class InitializeBundle:
    """The data pulled from the forge on Initialize: the head SHA at
    the moment the import happened plus every file's bytes."""

    head_sha: str
    files: list[DepositFile] = field(default_factory=list)
