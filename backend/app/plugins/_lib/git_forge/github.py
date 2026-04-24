"""GitHub adapter — single-commit push via the git-data API.

Unlike Forgejo/Gitea's batch ``POST /contents``, GitHub has no
batch Contents endpoint. To honour Aracne2's "one commit always"
invariant we drive the low-level git-data API:

1. Resolve the target branch's HEAD and its tree SHA.
2. Upload each file as a blob (``POST /git/blobs``).
3. Compose a new tree on top of the old one
   (``POST /git/trees`` with ``base_tree`` + the blob entries).
4. Create a commit pointing at the new tree
   (``POST /git/commits`` with ``parents=[HEAD]`` — or none for a
   first push on an empty branch).
5. Move the ref (``PATCH /git/refs/heads/<branch>`` for updates,
   ``POST /git/refs`` for first pushes).

Files present on the remote but not in our manifest are left alone —
the base-tree inheritance keeps them. This matches Codeberg's
batch semantics so the two forges behave identically from the
editor's perspective.

Initialize mirrors Codeberg: walk the recursive tree, fetch every
blob via ``GET /git/blobs/{sha}`` (which returns base64-encoded
content) and hand the bundle back to the caller. ``git/blobs`` is
capped at 100 MB per blob by GitHub; the plugin service applies its
own 10 MB import cap on top.

Auth: ``Authorization: Bearer <PAT>`` (the modern classic/fine-grained
PAT format). Both legacy ``token`` prefix and ``Bearer`` work; we
use ``Bearer`` to match fine-grained PATs.
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
    DepositFile,
    DepositManifest,
    InitializeBundle,
    RepoRef,
)

logger = structlog.get_logger()

_TIMEOUT = 30.0
_USER_AGENT = "Aracne2-GitHub/1.0"
_GITHUB_API = "https://api.github.com"
# Normal file blob mode — GitHub rejects anything else from us here.
_BLOB_MODE_FILE = "100644"


class GithubAdapter:
    """REST v3 adapter for github.com and GitHub Enterprise Server.

    ``repo.base_url`` should be ``https://github.com`` for the public
    service, or the GHE instance root (e.g. ``https://ghe.acme.com``).
    The API base is derived by swapping ``/`` for ``/api/v3/`` on
    GHE, or ``api.github.com`` for github.com — :meth:`_api_base`
    encodes that logic.
    """

    forge_id = "github"

    async def push_manifest(
        self,
        *,
        repo: RepoRef,
        manifest: DepositManifest,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> CommitResult:
        head = await self.get_head_sha(
            repo=repo, branch=manifest.branch, token=token, transport=transport,
        )
        base_tree_sha: str | None = None
        parents: list[str] = []
        if head is not None:
            parents = [head]
            base_tree_sha = await self._tree_sha_of_commit(
                repo=repo, commit_sha=head, token=token, transport=transport,
            )

        # 1. Upload each file as a blob (base64).
        blob_shas: dict[str, str] = {}  # path → blob sha
        async with self._client(token, transport) as client:
            for f in manifest.files:
                resp = await client.post(
                    self._api(repo, "git/blobs"),
                    json={
                        "content": base64.b64encode(f.content).decode("ascii"),
                        "encoding": "base64",
                    },
                )
                self._raise_for_status(resp)
                data = resp.json()
                sha = data.get("sha") if isinstance(data, dict) else None
                if not isinstance(sha, str) or not sha:
                    raise UpstreamError(
                        f"GitHub returned a blob without a SHA for {f.path}",
                    )
                blob_shas[f.path] = sha

            # 2. Compose the new tree on top of the old one.
            tree_body: dict[str, Any] = {
                "tree": [
                    {
                        "path": path,
                        "mode": _BLOB_MODE_FILE,
                        "type": "blob",
                        "sha": sha,
                    }
                    for path, sha in blob_shas.items()
                ],
            }
            if base_tree_sha is not None:
                tree_body["base_tree"] = base_tree_sha
            resp = await client.post(
                self._api(repo, "git/trees"), json=tree_body,
            )
            self._raise_for_status(resp)
            tree_data = resp.json()
            new_tree_sha = (
                tree_data.get("sha") if isinstance(tree_data, dict) else None
            )
            if not isinstance(new_tree_sha, str) or not new_tree_sha:
                raise UpstreamError("GitHub tree creation returned no SHA")

            # 3. Create the commit.
            commit_body: dict[str, Any] = {
                "message": manifest.commit_message,
                "tree": new_tree_sha,
                "parents": parents,
                "author": {
                    "name": manifest.committer_name,
                    "email": manifest.committer_email,
                },
                "committer": {
                    "name": manifest.committer_name,
                    "email": manifest.committer_email,
                },
            }
            resp = await client.post(
                self._api(repo, "git/commits"), json=commit_body,
            )
            self._raise_for_status(resp)
            commit_data = resp.json()
            commit_sha = (
                commit_data.get("sha") if isinstance(commit_data, dict) else None
            )
            if not isinstance(commit_sha, str) or not commit_sha:
                raise UpstreamError("GitHub commit creation returned no SHA")

            # 4. Move (or create) the ref.
            ref_path = f"git/refs/heads/{manifest.branch}"
            if head is None:
                resp = await client.post(
                    self._api(repo, "git/refs"),
                    json={
                        "ref": f"refs/heads/{manifest.branch}",
                        "sha": commit_sha,
                    },
                )
            else:
                resp = await client.patch(
                    self._api(repo, ref_path),
                    json={"sha": commit_sha, "force": False},
                )
            self._raise_for_status(resp)

        html_url = (
            commit_data.get("html_url") if isinstance(commit_data, dict) else None
        )
        committed_at = datetime.now(UTC)
        # ``committer.date`` is authoritative when present.
        if isinstance(commit_data, dict):
            committer = commit_data.get("committer") or {}
            date_str = committer.get("date") if isinstance(committer, dict) else None
            if isinstance(date_str, str):
                try:
                    committed_at = datetime.fromisoformat(
                        date_str.replace("Z", "+00:00"),
                    )
                except ValueError:
                    pass

        return CommitResult(
            sha=commit_sha, committed_at=committed_at, html_url=html_url,
        )

    async def get_head_sha(
        self,
        *,
        repo: RepoRef,
        branch: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> str | None:
        async with self._client(token, transport) as client:
            resp = await client.get(self._api(repo, f"branches/{branch}"))
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        data = resp.json()
        if isinstance(data, dict):
            commit = data.get("commit")
            if isinstance(commit, dict):
                sha = commit.get("sha")
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

        tree_sha = await self._tree_sha_of_commit(
            repo=repo, commit_sha=head, token=token, transport=transport,
        )
        if tree_sha is None:
            return InitializeBundle(head_sha=head, files=[])

        async with self._client(token, transport) as client:
            resp = await client.get(
                self._api(repo, f"git/trees/{tree_sha}"),
                params={"recursive": "1"},
            )
            self._raise_for_status(resp)
            tree = resp.json()
            entries: list[tuple[str, str]] = []
            if isinstance(tree, dict):
                for item in tree.get("tree", []) or []:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "blob":
                        continue
                    path = item.get("path")
                    sha = item.get("sha")
                    if isinstance(path, str) and isinstance(sha, str):
                        entries.append((path, sha))

            files: list[DepositFile] = []
            for path, blob_sha in entries:
                blob_resp = await client.get(
                    self._api(repo, f"git/blobs/{blob_sha}"),
                )
                if blob_resp.status_code == 404:
                    # Vanished between listing and fetch — skip.
                    continue
                self._raise_for_status(blob_resp)
                blob = blob_resp.json()
                content_b64 = blob.get("content") if isinstance(blob, dict) else None
                encoding = blob.get("encoding") if isinstance(blob, dict) else None
                if not isinstance(content_b64, str):
                    continue
                if encoding == "base64":
                    try:
                        content = base64.b64decode(content_b64)
                    except Exception:  # pragma: no cover — defensive
                        continue
                else:
                    # GitHub sometimes ships ``utf-8`` for tiny text blobs.
                    content = content_b64.encode("utf-8")
                files.append(DepositFile(path=path, content=content))

        return InitializeBundle(head_sha=head, files=files)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _tree_sha_of_commit(
        self,
        *,
        repo: RepoRef,
        commit_sha: str,
        token: str,
        transport: httpx.AsyncBaseTransport | None,
    ) -> str | None:
        async with self._client(token, transport) as client:
            resp = await client.get(
                self._api(repo, f"git/commits/{commit_sha}"),
            )
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)
        data = resp.json()
        if isinstance(data, dict):
            tree = data.get("tree")
            if isinstance(tree, dict):
                sha = tree.get("sha")
                if isinstance(sha, str) and sha:
                    return sha
        return None

    def _api_base(self, repo: RepoRef) -> str:
        base = repo.base_url.rstrip("/")
        # Public github.com — standard API host.
        if base == "https://github.com" or base == "http://github.com":
            return _GITHUB_API
        # GitHub Enterprise Server — the API is under /api/v3/ on the
        # same host.
        return f"{base}/api/v3"

    def _api(self, repo: RepoRef, tail: str) -> str:
        return f"{self._api_base(repo)}/repos/{repo.owner}/{repo.name}/{tail}"

    def _client(
        self,
        token: str,
        transport: httpx.AsyncBaseTransport | None,
    ) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": _USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
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
            raise AuthFailed("GitHub rejected the token")
        if code == 403:
            # GitHub's 403 covers both rate-limit and missing-scope —
            # disambiguate via the canonical header set.
            if (
                resp.headers.get("x-ratelimit-remaining") == "0"
                or "rate limit" in resp.text.lower()
            ):
                raise RateLimited("GitHub rate-limited the request")
            raise Forbidden("Token lacks the scope for this operation")
        if code == 404:
            raise RepoNotFound("Repo or branch not found on GitHub")
        if code == 409:
            raise PushConflict("Branch moved under us; retry with fresh head")
        if code == 422:
            # Invalid ref update / stale expected SHA on PATCH refs.
            raise PushConflict("Ref update rejected; branch likely moved")
        if code == 429:
            raise RateLimited("GitHub rate-limited the request")
        raise UpstreamError(
            f"GitHub returned HTTP {code}: {resp.text[:200]}"
        )
