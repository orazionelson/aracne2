"""GitLab adapter — single-commit push via the commits batch API.

GitLab's REST v4 exposes
``POST /projects/:id/repository/commits`` which accepts an ordered
``actions`` array (``create`` / ``update`` / ``delete`` / ``move`` /
``chmod``). Every call produces exactly one commit regardless of
how many files are touched — a direct match for Aracne2's
"one commit always" invariant, just like Forgejo's batch Contents
endpoint.

Project identifier: GitLab accepts either a numeric ID or a
URL-encoded ``namespace%2Fproject`` path. The plugin stores
``owner``/``name`` separately; the adapter joins and URL-encodes
them at call time. This naturally handles nested group paths
(``group/subgroup/project``) if a deployment stores the group path
in ``owner``.

Initialize mirrors Codeberg: walk the recursive tree (paginated),
fetch each blob via the raw-file endpoint, hand the bundle back.

Auth: ``Authorization: Bearer <PAT>`` (GitLab also accepts
``PRIVATE-TOKEN: <PAT>``; Bearer works for both classic PATs and
project-access tokens).
"""

from __future__ import annotations

import base64
import urllib.parse
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
    DepositFile,
    DepositManifest,
    InitializeBundle,
    RepoRef,
)

logger = structlog.get_logger()

_TIMEOUT = 30.0
_USER_AGENT = "Aracne2-GitLab/1.0"
_TREE_PAGE_SIZE = 100
# Safety cap — enough for editorial-scale repos; Initialize stops at
# this many tree entries even if the upstream keeps paginating.
_MAX_TREE_PAGES = 200


class GitlabAdapter:
    """REST v4 adapter for gitlab.com and self-hosted GitLab.

    ``repo.base_url`` should be ``https://gitlab.com`` for the public
    service, or the self-hosted GitLab instance root (e.g.
    ``https://gitlab.example.edu``). The API lives at
    ``<base>/api/v4/`` on every GitLab install.
    """

    forge_id = "gitlab"

    async def push_manifest(
        self,
        *,
        repo: RepoRef,
        manifest: DepositManifest,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> CommitResult:
        # Figure out which paths already exist on the target branch so
        # each action can be marked create vs. update correctly —
        # GitLab rejects mismatched action/state with 400.
        head = await self.get_head_sha(
            repo=repo, branch=manifest.branch, token=token, transport=transport,
        )
        existing: set[str] = set()
        if head is not None:
            existing = await self._list_paths_at_ref(
                repo=repo, ref=head, token=token, transport=transport,
            )

        actions: list[dict[str, Any]] = []
        for f in manifest.files:
            action = "update" if f.path in existing else "create"
            actions.append({
                "action": action,
                "file_path": f.path,
                "content": base64.b64encode(f.content).decode("ascii"),
                "encoding": "base64",
            })

        body: dict[str, Any] = {
            "branch": manifest.branch,
            "commit_message": manifest.commit_message,
            "author_name": manifest.committer_name,
            "author_email": manifest.committer_email,
            "actions": actions,
        }
        # When pushing to a fresh branch on a non-empty repo, GitLab
        # wants ``start_branch`` to know which ref to fork from. Empty
        # repos don't need it — the commit creates the ref outright.
        if head is None:
            # Attempt to start from the repo's default branch so a
            # first push of ``main`` against a repo whose default is
            # ``main`` still works; if the branch is genuinely new and
            # the repo is empty, GitLab ignores this field.
            body["start_branch"] = manifest.branch

        url = self._url(repo, "repository/commits")
        async with self._client(token, transport) as client:
            resp = await client.post(url, json=body)

        self._raise_for_status(resp)
        data = resp.json() if resp.content else {}
        sha = ""
        html_url: str | None = None
        committed_at = datetime.now(UTC)
        if isinstance(data, dict):
            sha = str(data.get("id") or "")
            html_url = data.get("web_url")
            created = data.get("created_at") or data.get("committed_date")
            if isinstance(created, str):
                try:
                    committed_at = datetime.fromisoformat(
                        created.replace("Z", "+00:00"),
                    )
                except ValueError:
                    pass
        if not sha:
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
        encoded_branch = urllib.parse.quote(branch, safe="")
        url = self._url(repo, f"repository/branches/{encoded_branch}")
        async with self._client(token, transport) as client:
            resp = await client.get(url)
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        data = resp.json()
        if isinstance(data, dict):
            commit = data.get("commit")
            if isinstance(commit, dict):
                sha = commit.get("id")
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
        head = await self.get_head_sha(
            repo=repo, branch=branch, token=token, transport=transport,
        )
        if head is None:
            return InitializeBundle(head_sha="", files=[])

        paths = await self._list_paths_at_ref(
            repo=repo, ref=head, token=token, transport=transport,
        )

        files: list[DepositFile] = []
        async with self._client(token, transport) as client:
            for path in sorted(paths):
                # /projects/:id/repository/files/:file_path/raw?ref=<sha>
                encoded_path = urllib.parse.quote(path, safe="")
                raw_url = self._url(
                    repo, f"repository/files/{encoded_path}/raw",
                )
                resp = await client.get(raw_url, params={"ref": head})
                if resp.status_code == 404:
                    # Vanished between tree listing and fetch — skip.
                    continue
                self._raise_for_status(resp)
                files.append(DepositFile(path=path, content=resp.content))

        return InitializeBundle(head_sha=head, files=files)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _list_paths_at_ref(
        self,
        *,
        repo: RepoRef,
        ref: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None,
    ) -> set[str]:
        """Walk the recursive tree at ``ref`` and return the set of
        blob paths. Follows the ``x-next-page`` header to paginate
        through arbitrarily large repositories (capped at
        ``_MAX_TREE_PAGES``)."""
        paths: set[str] = set()
        async with self._client(token, transport) as client:
            page = 1
            while page <= _MAX_TREE_PAGES:
                resp = await client.get(
                    self._url(repo, "repository/tree"),
                    params={
                        "ref": ref,
                        "recursive": "true",
                        "per_page": str(_TREE_PAGE_SIZE),
                        "page": str(page),
                    },
                )
                if resp.status_code == 404:
                    return paths
                self._raise_for_status(resp)
                items = resp.json()
                if not isinstance(items, list) or not items:
                    break
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "blob":
                        continue
                    path = item.get("path")
                    if isinstance(path, str):
                        paths.add(path)
                next_page = resp.headers.get("x-next-page")
                if not next_page or next_page == "":
                    break
                try:
                    page = int(next_page)
                except ValueError:
                    break
        return paths

    def _url(self, repo: RepoRef, tail: str) -> str:
        base = repo.base_url.rstrip("/")
        project = urllib.parse.quote(
            f"{repo.owner}/{repo.name}", safe="",
        )
        return f"{base}/api/v4/projects/{project}/{tail}"

    def _client(
        self,
        token: str,
        transport: httpx.AsyncBaseTransport | None,
    ) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
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
            raise AuthFailed("GitLab rejected the token")
        if code == 403:
            raise Forbidden("Token lacks the scope for this operation")
        if code == 404:
            raise RepoNotFound("Project or branch not found on GitLab")
        if code == 400:
            # GitLab uses 400 for "file already exists" on create or
            # "file not found" on update — both mean our tree snapshot
            # went stale mid-push.
            raise PushConflict(
                "GitLab rejected the commit; tree likely changed "
                "between snapshot and push"
            )
        if code == 409:
            raise PushConflict("Branch moved under us; retry with fresh head")
        if code == 429:
            raise RateLimited("GitLab rate-limited the request")
        raise UpstreamError(
            f"GitLab returned HTTP {code}: {resp.text[:200]}"
        )
