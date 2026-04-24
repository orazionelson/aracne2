"""GitHub adapter — no network, ``httpx.MockTransport``.

Exercises both the push flow (blob → tree → commit → ref update /
create) and the initialize flow (tree walk + blob fetch). Error
mapping is checked for every status the adapter disambiguates,
including the 403-means-rate-limit branch GitHub overloads.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.plugins._lib.git_forge.errors import (
    AuthFailed,
    Forbidden,
    PushConflict,
    RateLimited,
    RepoNotFound,
    UpstreamError,
)
from app.plugins._lib.git_forge.github import GithubAdapter
from app.plugins._lib.git_forge.models import (
    DepositFile,
    DepositManifest,
    RepoRef,
)


def _repo(base: str = "https://github.com") -> RepoRef:
    return RepoRef(base_url=base, owner="alice", name="edition")


def _manifest(files: list[DepositFile] | None = None) -> DepositManifest:
    return DepositManifest(
        files=files or [DepositFile(path="documents/a.xml", content=b"<a/>")],
        branch="main",
        commit_message="Aracne2 sync",
        committer_name="Aracne2",
        committer_email="aracne2@example.org",
    )


# ── Update push: branch exists → blobs → tree → commit → PATCH ref ────────


@pytest.mark.asyncio
async def test_push_existing_branch_full_pipeline() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        seen_paths.append(f"{method} {path}")
        if path.endswith("/branches/main"):
            return httpx.Response(
                200, json={"commit": {"sha": "head-sha"}},
            )
        if path.endswith("/git/commits/head-sha"):
            return httpx.Response(
                200, json={"tree": {"sha": "old-tree-sha"}},
            )
        if method == "POST" and path.endswith("/git/blobs"):
            body = json.loads(request.content)
            assert body["encoding"] == "base64"
            content = base64.b64decode(body["content"])
            return httpx.Response(
                201, json={"sha": f"blob-{content.decode()}"},
            )
        if method == "POST" and path.endswith("/git/trees"):
            body = json.loads(request.content)
            assert body["base_tree"] == "old-tree-sha"
            # Every entry carries mode 100644 + type blob + blob sha.
            assert all(e["mode"] == "100644" for e in body["tree"])
            assert all(e["type"] == "blob" for e in body["tree"])
            return httpx.Response(201, json={"sha": "new-tree-sha"})
        if method == "POST" and path.endswith("/git/commits"):
            body = json.loads(request.content)
            assert body["tree"] == "new-tree-sha"
            assert body["parents"] == ["head-sha"]
            return httpx.Response(
                201,
                json={
                    "sha": "new-commit-sha",
                    "html_url": "https://github.com/alice/edition/commit/new-commit-sha",
                    "committer": {"date": "2026-04-24T10:00:00Z"},
                },
            )
        if method == "PATCH" and path.endswith("/git/refs/heads/main"):
            return httpx.Response(200, json={"ref": "refs/heads/main"})
        raise AssertionError(f"Unexpected: {method} {path}")

    adapter = GithubAdapter()
    manifest = _manifest(
        [
            DepositFile(path="documents/<a/>", content=b"<a/>"),
            DepositFile(path="documents/<b/>", content=b"<b/>"),
        ]
    )
    result = await adapter.push_manifest(
        repo=_repo(), manifest=manifest, token="PAT",
        transport=httpx.MockTransport(handler),
    )
    assert result.sha == "new-commit-sha"
    assert result.html_url is not None
    # Sanity: all five pipeline stages were hit, in order, in the same
    # async client session.
    assert any("branches/main" in s for s in seen_paths)
    assert any("git/commits/head-sha" in s for s in seen_paths)
    assert sum("POST" in s and "git/blobs" in s for s in seen_paths) == 2
    assert any("POST" in s and "git/trees" in s for s in seen_paths)
    assert any("PATCH" in s and "git/refs/heads/main" in s for s in seen_paths)


# ── First push: branch 404 → no base_tree, no parents, POST refs ──────────


@pytest.mark.asyncio
async def test_push_first_commit_uses_no_parent_and_posts_ref() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if path.endswith("/branches/main"):
            return httpx.Response(404, json={"message": "Branch not found"})
        if method == "POST" and path.endswith("/git/blobs"):
            return httpx.Response(201, json={"sha": "blob-1"})
        if method == "POST" and path.endswith("/git/trees"):
            body = json.loads(request.content)
            # First push has no base_tree.
            assert "base_tree" not in body
            return httpx.Response(201, json={"sha": "t1"})
        if method == "POST" and path.endswith("/git/commits"):
            body = json.loads(request.content)
            assert body["parents"] == []
            return httpx.Response(201, json={"sha": "c1"})
        if method == "POST" and path.endswith("/git/refs"):
            body = json.loads(request.content)
            assert body["ref"] == "refs/heads/main"
            assert body["sha"] == "c1"
            return httpx.Response(201, json={"ref": "refs/heads/main"})
        raise AssertionError(f"Unexpected: {method} {path}")

    adapter = GithubAdapter()
    result = await adapter.push_manifest(
        repo=_repo(), manifest=_manifest(), token="PAT",
        transport=httpx.MockTransport(handler),
    )
    assert result.sha == "c1"


# ── Bearer auth header ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_header_is_bearer_pat() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        captured["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(404)

    adapter = GithubAdapter()
    await adapter.get_head_sha(
        repo=_repo(), branch="main", token="PAT",
        transport=httpx.MockTransport(handler),
    )
    assert captured["auth"] == "Bearer PAT"
    assert captured["ua"].startswith("Aracne2-GitHub")


# ── GHE base URL routing ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ghe_base_url_routes_api_under_api_v3() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        captured["path"] = request.url.path
        return httpx.Response(404)

    adapter = GithubAdapter()
    await adapter.get_head_sha(
        repo=_repo("https://ghe.acme.com"), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert captured["host"] == "ghe.acme.com"
    assert captured["path"].startswith("/api/v3/repos/alice/edition/")


@pytest.mark.asyncio
async def test_public_github_routes_api_to_api_github_com() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        return httpx.Response(404)

    adapter = GithubAdapter()
    await adapter.get_head_sha(
        repo=_repo("https://github.com"), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert captured["host"] == "api.github.com"


# ── Initialize flow ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_bundle_empty_repo_is_empty() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    adapter = GithubAdapter()
    bundle = await adapter.initialize_bundle(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert bundle.head_sha == ""
    assert bundle.files == []


@pytest.mark.asyncio
async def test_initialize_walks_tree_and_decodes_base64_blobs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"sha": "h"}})
        if path.endswith("/git/commits/h"):
            return httpx.Response(200, json={"tree": {"sha": "t"}})
        if path.endswith("/git/trees/t"):
            return httpx.Response(200, json={"tree": [
                {"path": "documents/a.xml", "sha": "ba", "type": "blob"},
                {"path": "documents/b.xml", "sha": "bb", "type": "blob"},
                {"path": "src", "sha": "tt", "type": "tree"},  # skipped
            ]})
        if path.endswith("/git/blobs/ba"):
            return httpx.Response(200, json={
                "content": base64.b64encode(b"<a/>").decode("ascii"),
                "encoding": "base64",
            })
        if path.endswith("/git/blobs/bb"):
            return httpx.Response(200, json={
                "content": base64.b64encode(b"<b/>").decode("ascii"),
                "encoding": "base64",
            })
        raise AssertionError(f"Unexpected: {path}")

    adapter = GithubAdapter()
    bundle = await adapter.initialize_bundle(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert bundle.head_sha == "h"
    by_path = {f.path: f.content for f in bundle.files}
    assert by_path == {
        "documents/a.xml": b"<a/>",
        "documents/b.xml": b"<b/>",
    }


@pytest.mark.asyncio
async def test_initialize_skips_blob_that_vanishes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"sha": "h"}})
        if path.endswith("/git/commits/h"):
            return httpx.Response(200, json={"tree": {"sha": "t"}})
        if path.endswith("/git/trees/t"):
            return httpx.Response(200, json={"tree": [
                {"path": "a.xml", "sha": "ba", "type": "blob"},
                {"path": "b.xml", "sha": "bb", "type": "blob"},
            ]})
        if path.endswith("/git/blobs/ba"):
            return httpx.Response(404)
        if path.endswith("/git/blobs/bb"):
            return httpx.Response(200, json={
                "content": base64.b64encode(b"<b/>").decode("ascii"),
                "encoding": "base64",
            })
        raise AssertionError(f"Unexpected: {path}")

    adapter = GithubAdapter()
    bundle = await adapter.initialize_bundle(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert [f.path for f in bundle.files] == ["b.xml"]


# ── Error mapping ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_403_with_ratelimit_header_surfaces_as_rate_limited() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0"},
            json={"message": "rate limit"},
        )

    adapter = GithubAdapter()
    with pytest.raises(RateLimited):
        await adapter.get_head_sha(
            repo=_repo(), branch="main", token="T",
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_403_without_ratelimit_hint_is_forbidden() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "scope missing"})

    adapter = GithubAdapter()
    with pytest.raises(Forbidden):
        await adapter.get_head_sha(
            repo=_repo(), branch="main", token="T",
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [
        (401, AuthFailed),
        (404, RepoNotFound),
        (409, PushConflict),
        (422, PushConflict),
        (429, RateLimited),
        (500, UpstreamError),
    ],
)
async def test_push_error_mapping_on_post_blob(
    status: int, expected: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"sha": "h"}})
        if request.url.path.endswith("/git/commits/h"):
            return httpx.Response(200, json={"tree": {"sha": "t"}})
        # Blob upload fails with the parametrised status.
        return httpx.Response(status, json={"message": "x"})

    adapter = GithubAdapter()
    with pytest.raises(expected):
        await adapter.push_manifest(
            repo=_repo(), manifest=_manifest(), token="T",
            transport=httpx.MockTransport(handler),
        )
