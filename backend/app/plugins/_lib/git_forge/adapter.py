"""Protocol every git-forge adapter must satisfy.

The three concrete adapters (Codeberg/Forgejo, GitHub, GitLab) speak
different REST APIs under the hood but expose the same async surface
to the plugin services. Phase 1 implements only ``push_manifest`` and
``get_head_sha``; Phase 2 adds ``list_tree`` and ``fetch_file`` for
the Initialize flow.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from app.plugins._lib.git_forge.models import (
    CommitResult,
    DepositManifest,
    InitializeBundle,
    RepoRef,
)


class GitForgeAdapter(Protocol):
    """The adapter contract.

    ``transport`` is an optional httpx.AsyncBaseTransport for tests
    (httpx.MockTransport). The token is already resolved by the
    caller (per-link override wins over plugin-global PAT).
    """

    forge_id: str
    """Stable identifier used for logging (``codeberg``, ``github``, ``gitlab``)."""

    async def push_manifest(
        self,
        *,
        repo: RepoRef,
        manifest: DepositManifest,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> CommitResult:
        """Create a **single** commit on ``manifest.branch`` that
        contains every file in ``manifest.files``.

        Raises ``AuthFailed`` / ``Forbidden`` / ``RepoNotFound`` /
        ``BranchNotFound`` / ``RateLimited`` / ``PushConflict`` /
        ``UpstreamError`` depending on the upstream response.
        """
        ...

    async def get_head_sha(
        self,
        *,
        repo: RepoRef,
        branch: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> str | None:
        """Return the SHA of ``branch``'s tip, or ``None`` when the
        repo is empty / the branch does not exist. Used by the push
        orchestrator to decide between "first push" (create branch)
        and "update push" (add commit on top)."""
        ...

    async def initialize_bundle(
        self,
        *,
        repo: RepoRef,
        branch: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> InitializeBundle:
        """Return every file currently on ``branch`` plus the head
        SHA, so the caller can import the repo into an empty Aracne2
        collection. Phase 2 — safe to raise ``NotImplementedError``
        in Phase-1 adapters.
        """
        ...
