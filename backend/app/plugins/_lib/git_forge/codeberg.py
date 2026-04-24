"""Codeberg (Forgejo/Gitea) adapter.

The Forgejo/Gitea REST API exposes a batch endpoint that accepts a
list of create/update/delete operations and resolves them into a
**single commit** — exactly matching Aracne2's "one commit always"
invariant. See the Forgejo swagger at
``https://codeberg.org/api/swagger#/repository/repoChangeFiles``.

Endpoints used:

- ``GET  /repos/{owner}/{repo}/branches/{branch}``
    → head SHA (404 when branch absent, 404 when repo absent)
- ``POST /repos/{owner}/{repo}/contents``
    → batch commit with ``create|update|delete`` operations

All bodies are JSON; file contents are base64-encoded.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.plugins._lib.git_forge.errors import (
    AuthFailed,
    BranchNotFound,
    Forbidden,
    PushConflict,
    RateLimited,
    RepoNotFound,
    UpstreamError,
)
from app.plugins._lib.git_forge.models import (
    CommitResult,
    DepositManifest,
    InitializeBundle,
    RepoRef,
)

logger = structlog.get_logger()

_TIMEOUT = 30.0
_USER_AGENT = "Aracne2-Codeberg/1.0"


class CodebergAdapter:
    """Forgejo/Gitea REST adapter (Codeberg and any self-hosted Forgejo)."""

    forge_id = "codeberg"

    async def push_manifest(
        self,
        *,
        repo: RepoRef,
        manifest: DepositManifest,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> CommitResult:
        # Resolve existing HEAD so we can switch the per-file operation
        # between ``create`` (file absent) and ``update`` (file present
        # with its old SHA). Forgejo's batch endpoint requires the
        # per-file ``sha`` on updates.
        head = await self.get_head_sha(
            repo=repo, branch=manifest.branch, token=token, transport=transport,
        )
        existing: dict[str, str] = {}
        if head is not None:
            existing = await self._list_file_shas_at_ref(
                repo=repo, ref=head, token=token, transport=transport,
            )

        files_payload: list[dict[str, Any]] = []
        for f in manifest.files:
            op = "update" if f.path in existing else "create"
            entry: dict[str, Any] = {
                "operation": op,
                "path": f.path,
                "content": base64.b64encode(f.content).decode("ascii"),
            }
            if op == "update":
                entry["sha"] = existing[f.path]
            files_payload.append(entry)

        body: dict[str, Any] = {
            "branch": manifest.branch,
            "message": manifest.commit_message,
            "author": {
                "name": manifest.committer_name,
                "email": manifest.committer_email,
            },
            "committer": {
                "name": manifest.committer_name,
                "email": manifest.committer_email,
            },
            "files": files_payload,
        }

        url = self._url(repo, "contents")
        async with self._client(token, transport) as client:
            resp = await client.post(url, json=body)

        self._raise_for_status(resp)
        data = resp.json()
        commit = data.get("commit") if isinstance(data, dict) else None
        sha = ""
        html_url: str | None = None
        committed_at: datetime = datetime.now(UTC)
        if isinstance(commit, dict):
            sha = str(commit.get("sha") or "")
            html_url = commit.get("html_url") or commit.get("url")
            created = commit.get("created") or commit.get("timestamp")
            if isinstance(created, str):
                try:
                    committed_at = datetime.fromisoformat(
                        created.replace("Z", "+00:00")
                    )
                except ValueError:
                    committed_at = datetime.now(UTC)
        if not sha:
            # Fall back to branch head — some Forgejo versions return
            # the commit under ``verification`` or differently named keys.
            refreshed = await self.get_head_sha(
                repo=repo, branch=manifest.branch, token=token, transport=transport,
            )
            sha = refreshed or ""
        return CommitResult(sha=sha, committed_at=committed_at, html_url=html_url)

    async def get_head_sha(
        self,
        *,
        repo: RepoRef,
        branch: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> str | None:
        url = self._url(repo, f"branches/{branch}")
        async with self._client(token, transport) as client:
            resp = await client.get(url)
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        data = resp.json()
        if isinstance(data, dict):
            commit = data.get("commit")
            if isinstance(commit, dict):
                sha = commit.get("id") or commit.get("sha")
                if isinstance(sha, str) and sha:
                    return sha
        return None

    async def initialize_bundle(
        self,
        *,
        repo: RepoRef,
        branch: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> InitializeBundle:
        raise NotImplementedError(
            "Initialize flow ships in Phase 2 of the git-forge plugins."
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _list_file_shas_at_ref(
        self,
        *,
        repo: RepoRef,
        ref: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None,
    ) -> dict[str, str]:
        """Walk the repo tree at ``ref`` and return ``{path: blob_sha}``.

        Forgejo's ``git/trees/{sha}?recursive=true`` is the cheapest
        full-tree fetch; every returned tree item carries its path and
        sha. Used to populate the ``sha`` field on ``update`` operations
        in the batch commit payload.
        """
        url = self._url(repo, f"git/trees/{ref}")
        async with self._client(token, transport) as client:
            resp = await client.get(url, params={"recursive": "true"})
        if resp.status_code == 404:
            return {}
        self._raise_for_status(resp)
        data = resp.json()
        out: dict[str, str] = {}
        if isinstance(data, dict):
            tree = data.get("tree", [])
            if isinstance(tree, list):
                for item in tree:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "blob":
                        continue
                    path = item.get("path")
                    sha = item.get("sha")
                    if isinstance(path, str) and isinstance(sha, str):
                        out[path] = sha
        return out

    def _url(self, repo: RepoRef, tail: str) -> str:
        base = repo.base_url.rstrip("/")
        return f"{base}/api/v1/repos/{repo.owner}/{repo.name}/{tail}"

    def _client(
        self,
        token: str,
        transport: httpx.AsyncBaseTransport | None,
    ) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"token {token}",
            "User-Agent": _USER_AGENT,
        }
        kwargs: dict[str, Any] = {
            "timeout": _TIMEOUT,
            "follow_redirects": True,
            "headers": headers,
        }
        if transport is not None:
            kwargs["transport"] = transport
        return httpx.AsyncClient(**kwargs)

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        code = resp.status_code
        if code == 401:
            raise AuthFailed("Codeberg rejected the token")
        if code == 403:
            raise Forbidden("Token lacks the scope for this operation")
        if code == 404:
            raise RepoNotFound("Repo or branch not found on Codeberg")
        if code == 409:
            raise PushConflict("Branch moved under us; retry with fresh head")
        if code == 422:
            # Forgejo uses 422 for stale SHA on updates — treat as push
            # conflict so the caller can retry after refreshing.
            raise PushConflict("Stale file SHA; repo changed during push")
        if code == 429:
            raise RateLimited("Codeberg rate-limited the request")
        raise UpstreamError(
            f"Codeberg returned HTTP {code}: {resp.text[:200]}"
        )
