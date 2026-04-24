"""GitLab adapter — no network, ``httpx.MockTransport``.

Covers the batch-commit flow, create-vs-update marking driven by a
prior tree snapshot, the project-path URL encoding, tree pagination
via ``x-next-page``, Initialize's raw-file fetch, and every status
the adapter special-cases.
"""

from __future__ import annotations

import base64
import json
import urllib.parse

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
from app.plugins._lib.git_forge.gitlab import GitlabAdapter
from app.plugins._lib.git_forge.models import (
    DepositFile,
    DepositManifest,
    RepoRef,
)


def _repo(base: str = "https://gitlab.com") -> RepoRef:
    return RepoRef(base_url=base, owner="alice", name="edition")


def _manifest(files: list[DepositFile] | None = None) -> DepositManifest:
    return DepositManifest(
        files=files or [DepositFile(path="documents/a.xml", content=b"<a/>")],
        branch="main",
        commit_message="Aracne2 sync",
        committer_name="Aracne2",
        committer_email="aracne2@example.org",
    )


# ── Project path URL-encoding ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_url_encodes_owner_name_into_percent2f() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # Use raw_path so the %2F survives — httpx's .path is decoded.
        captured["raw_path"] = request.url.raw_path.decode("ascii")
        return httpx.Response(404)

    adapter = GitlabAdapter()
    await adapter.get_head_sha(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert "/projects/alice%2Fedition/" in captured["raw_path"]


@pytest.mark.asyncio
async def test_nested_group_paths_in_owner_field_are_encoded() -> None:
    """Owner may hold a multi-segment GitLab group path
    (``group/subgroup``). All slashes must be encoded."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["raw_path"] = request.url.raw_path.decode("ascii")
        return httpx.Response(404)

    adapter = GitlabAdapter()
    await adapter.get_head_sha(
        repo=RepoRef(
            base_url="https://gitlab.com",
            owner="group/subgroup",
            name="edition",
        ),
        branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert "/projects/group%2Fsubgroup%2Fedition/" in captured["raw_path"]


# ── Auth header ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_header_is_bearer_pat() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(404)

    adapter = GitlabAdapter()
    await adapter.get_head_sha(
        repo=_repo(), branch="main", token="PAT",
        transport=httpx.MockTransport(handler),
    )
    assert captured["auth"] == "Bearer PAT"


# ── Self-hosted GitLab ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_self_hosted_gitlab_honours_base_url() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        captured["raw_path"] = request.url.raw_path.decode("ascii")
        return httpx.Response(404)

    adapter = GitlabAdapter()
    await adapter.get_head_sha(
        repo=_repo("https://gitlab.example.edu"),
        branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert captured["host"] == "gitlab.example.edu"
    assert captured["raw_path"].startswith(
        "/api/v4/projects/alice%2Fedition/",
    )


# ── First push: branch 404 → all actions 'create', start_branch set ──────


@pytest.mark.asyncio
async def test_push_first_commit_uses_create_actions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if path.endswith("/branches/main"):
            return httpx.Response(404, json={"message": "404 Not Found"})
        if method == "POST" and path.endswith("/repository/commits"):
            body = json.loads(request.content)
            assert body["branch"] == "main"
            assert body["start_branch"] == "main"
            for a in body["actions"]:
                assert a["action"] == "create"
                assert a["encoding"] == "base64"
            return httpx.Response(
                201,
                json={
                    "id": "commit-sha-1",
                    "web_url": "https://gitlab.com/alice/edition/-/commit/commit-sha-1",
                    "created_at": "2026-04-24T12:00:00.000Z",
                },
            )
        raise AssertionError(f"Unexpected: {method} {path}")

    adapter = GitlabAdapter()
    result = await adapter.push_manifest(
        repo=_repo(),
        manifest=_manifest([
            DepositFile(path="documents/a.xml", content=b"<a/>"),
            DepositFile(path="documents/b.xml", content=b"<b/>"),
        ]),
        token="PAT",
        transport=httpx.MockTransport(handler),
    )
    assert result.sha == "commit-sha-1"
    assert result.html_url and "gitlab.com" in result.html_url


# ── Update push: tree snapshot flags create vs update per file ────────────


@pytest.mark.asyncio
async def test_push_update_marks_existing_paths_as_update() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"id": "head-sha"}})
        if path.endswith("/repository/tree"):
            return httpx.Response(
                200,
                headers={"x-next-page": ""},
                json=[
                    {"path": "documents/a.xml", "type": "blob"},
                    {"path": "README.md", "type": "blob"},
                    # A sub-tree must be ignored.
                    {"path": "documents", "type": "tree"},
                ],
            )
        if method == "POST" and path.endswith("/repository/commits"):
            body = json.loads(request.content)
            # start_branch must NOT be set on an update push.
            assert "start_branch" not in body
            actions_by_path = {a["file_path"]: a for a in body["actions"]}
            assert actions_by_path["documents/a.xml"]["action"] == "update"
            assert actions_by_path["documents/b.xml"]["action"] == "create"
            decoded = base64.b64decode(
                actions_by_path["documents/a.xml"]["content"],
            )
            assert decoded == b"<updated/>"
            return httpx.Response(
                201, json={"id": "new-head-sha", "created_at": "2026-04-24T12:00:00Z"},
            )
        raise AssertionError(f"Unexpected: {method} {path}")

    adapter = GitlabAdapter()
    result = await adapter.push_manifest(
        repo=_repo(),
        manifest=_manifest([
            DepositFile(path="documents/a.xml", content=b"<updated/>"),
            DepositFile(path="documents/b.xml", content=b"<b/>"),
        ]),
        token="T",
        transport=httpx.MockTransport(handler),
    )
    assert result.sha == "new-head-sha"


# ── Tree pagination ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_paths_follows_next_page_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        if request.url.path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"id": "h"}})
        if request.url.path.endswith("/repository/tree"):
            if page == "1":
                return httpx.Response(
                    200,
                    headers={"x-next-page": "2"},
                    json=[{"path": "a.xml", "type": "blob"}],
                )
            if page == "2":
                return httpx.Response(
                    200,
                    headers={"x-next-page": ""},
                    json=[{"path": "b.xml", "type": "blob"}],
                )
        if request.url.path.endswith("/repository/commits"):
            return httpx.Response(201, json={"id": "new"})
        raise AssertionError(f"Unexpected: {request.url}")

    adapter = GitlabAdapter()
    # Exercise the pagination via a push that requires the tree walk.
    await adapter.push_manifest(
        repo=_repo(), manifest=_manifest([
            DepositFile(path="a.xml", content=b"1"),
            DepositFile(path="c.xml", content=b"3"),
        ]),
        token="T", transport=httpx.MockTransport(handler),
    )


# ── Initialize ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_empty_repo_is_empty() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    adapter = GitlabAdapter()
    bundle = await adapter.initialize_bundle(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert bundle.head_sha == ""
    assert bundle.files == []


@pytest.mark.asyncio
async def test_initialize_walks_tree_and_fetches_raw_blobs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Use raw_path so %2F-encoded segments stay encoded.
        raw = request.url.raw_path.decode("ascii")
        if "/branches/main" in raw:
            return httpx.Response(200, json={"commit": {"id": "h"}})
        if "/repository/tree" in raw:
            return httpx.Response(
                200,
                headers={"x-next-page": ""},
                json=[
                    {"path": "documents/a.xml", "type": "blob"},
                    {"path": "documents/b.xml", "type": "blob"},
                ],
            )
        enc_a = urllib.parse.quote("documents/a.xml", safe="")
        enc_b = urllib.parse.quote("documents/b.xml", safe="")
        if f"/repository/files/{enc_a}/raw" in raw:
            assert request.url.params.get("ref") == "h"
            return httpx.Response(200, content=b"<a/>")
        if f"/repository/files/{enc_b}/raw" in raw:
            return httpx.Response(200, content=b"<b/>")
        raise AssertionError(f"Unexpected: {raw}")

    adapter = GitlabAdapter()
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
        raw = request.url.raw_path.decode("ascii")
        if "/branches/main" in raw:
            return httpx.Response(200, json={"commit": {"id": "h"}})
        if "/repository/tree" in raw:
            return httpx.Response(200, headers={"x-next-page": ""}, json=[
                {"path": "a.xml", "type": "blob"},
                {"path": "b.xml", "type": "blob"},
            ])
        if "/files/a.xml/raw" in raw:
            return httpx.Response(404)
        if "/files/b.xml/raw" in raw:
            return httpx.Response(200, content=b"<b/>")
        raise AssertionError(f"Unexpected: {raw}")

    adapter = GitlabAdapter()
    bundle = await adapter.initialize_bundle(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert [f.path for f in bundle.files] == ["b.xml"]


# ── Error mapping ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [
        (401, AuthFailed),
        (403, Forbidden),
        (404, RepoNotFound),
        (400, PushConflict),
        (409, PushConflict),
        (429, RateLimited),
        (500, UpstreamError),
    ],
)
async def test_push_error_mapping(status: int, expected: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"id": "h"}})
        if request.url.path.endswith("/repository/tree"):
            return httpx.Response(200, headers={"x-next-page": ""}, json=[])
        return httpx.Response(status, json={"message": "nope"})

    adapter = GitlabAdapter()
    with pytest.raises(expected):
        await adapter.push_manifest(
            repo=_repo(), manifest=_manifest(), token="T",
            transport=httpx.MockTransport(handler),
        )
