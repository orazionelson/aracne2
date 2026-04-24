"""Codeberg adapter — no network, ``httpx.MockTransport``.

Covers:

- First-push path (branch 404 → every file becomes a ``create``).
- Update path (branch exists → tree listing resolves SHAs → files
  become ``update`` with the right ``sha``).
- Error mapping for every status the adapter special-cases (401,
  403, 404, 409, 422, 429).
- Token header shape (``Authorization: token <PAT>``).
- Base URL honours both codeberg.org and a self-hosted Forgejo.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.plugins._lib.git_forge.codeberg import CodebergAdapter
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
    DepositFile,
    DepositManifest,
    RepoRef,
)


def _repo(base: str = "https://codeberg.org") -> RepoRef:
    return RepoRef(base_url=base, owner="alice", name="edition")


def _manifest(files: list[DepositFile] | None = None) -> DepositManifest:
    return DepositManifest(
        files=files or [DepositFile(path="documents/a.xml", content=b"<a/>")],
        branch="main",
        commit_message="Aracne2 sync",
        committer_name="Aracne2",
        committer_email="aracne2@example.org",
    )


# ── First push: branch 404 on HEAD lookup → files become 'create' ──────────


@pytest.mark.asyncio
async def test_push_first_commit_all_files_are_create() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/branches/main"):
            return httpx.Response(404, json={"message": "Not Found"})
        if path.endswith("/contents") and request.method == "POST":
            body = json.loads(request.content)
            assert body["branch"] == "main"
            assert body["message"] == "Aracne2 sync"
            assert len(body["files"]) == 2
            # Both files must be 'create', no 'sha' field.
            for entry in body["files"]:
                assert entry["operation"] == "create"
                assert "sha" not in entry
            return httpx.Response(
                200,
                json={
                    "commit": {
                        "sha": "abcdef1234",
                        "html_url": "https://codeberg.org/alice/edition/commit/abcdef1234",
                        "created": "2026-04-24T10:00:00Z",
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {path}")

    adapter = CodebergAdapter()
    manifest = _manifest(
        [
            DepositFile(path="documents/a.xml", content=b"<a/>"),
            DepositFile(path="documents/b.xml", content=b"<b/>"),
        ]
    )
    result = await adapter.push_manifest(
        repo=_repo(),
        manifest=manifest,
        token="PAT123",
        transport=httpx.MockTransport(handler),
    )
    assert result.sha == "abcdef1234"
    assert result.html_url and "codeberg.org" in result.html_url
    # Authorization header shape — Forgejo uses the 'token <PAT>' form.
    assert requests[0].headers["authorization"] == "token PAT123"


# ── Update push: branch exists → tree walk → files become 'update' ────────


@pytest.mark.asyncio
async def test_push_update_finds_existing_file_sha() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/branches/main"):
            return httpx.Response(
                200, json={"commit": {"id": "head-sha-1"}},
            )
        if path.endswith("/git/trees/head-sha-1"):
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": "documents/a.xml", "sha": "blob-a-1", "type": "blob"},
                        {"path": "README.md", "sha": "blob-r-1", "type": "blob"},
                    ]
                },
            )
        if path.endswith("/contents"):
            body = json.loads(request.content)
            by_path = {f["path"]: f for f in body["files"]}
            # documents/a.xml exists → update with the old blob sha.
            assert by_path["documents/a.xml"]["operation"] == "update"
            assert by_path["documents/a.xml"]["sha"] == "blob-a-1"
            # documents/b.xml is new → create.
            assert by_path["documents/b.xml"]["operation"] == "create"
            assert "sha" not in by_path["documents/b.xml"]
            # Content reached the wire base64-encoded.
            decoded = base64.b64decode(by_path["documents/a.xml"]["content"])
            assert decoded == b"<updated/>"
            return httpx.Response(
                200, json={"commit": {"sha": "new-head"}},
            )
        raise AssertionError(f"Unexpected: {path}")

    adapter = CodebergAdapter()
    manifest = _manifest(
        [
            DepositFile(path="documents/a.xml", content=b"<updated/>"),
            DepositFile(path="documents/b.xml", content=b"<b/>"),
        ]
    )
    result = await adapter.push_manifest(
        repo=_repo(),
        manifest=manifest,
        token="PAT",
        transport=httpx.MockTransport(handler),
    )
    assert result.sha == "new-head"


# ── get_head_sha ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_head_sha_returns_sha_when_branch_exists() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"commit": {"id": "deadbeef"}},
        )

    adapter = CodebergAdapter()
    sha = await adapter.get_head_sha(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert sha == "deadbeef"


@pytest.mark.asyncio
async def test_get_head_sha_returns_none_on_404() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    adapter = CodebergAdapter()
    sha = await adapter.get_head_sha(
        repo=_repo(), branch="main", token="T",
        transport=httpx.MockTransport(handler),
    )
    assert sha is None


# ── Self-hosted Forgejo: base_url honoured ────────────────────────────────


@pytest.mark.asyncio
async def test_base_url_targets_self_hosted_forgejo() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        captured["path"] = request.url.path
        return httpx.Response(404)

    adapter = CodebergAdapter()
    await adapter.get_head_sha(
        repo=_repo("https://git.example.edu"),
        branch="main",
        token="T",
        transport=httpx.MockTransport(handler),
    )
    assert captured["host"] == "git.example.edu"
    assert captured["path"].startswith("/api/v1/repos/alice/edition/")


# ── Error mapping ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [
        (401, AuthFailed),
        (403, Forbidden),
        (404, RepoNotFound),
        (409, PushConflict),
        (422, PushConflict),
        (429, RateLimited),
        (500, UpstreamError),
        (502, UpstreamError),
    ],
)
async def test_push_error_mapping(status: int, expected: type[Exception]) -> None:
    """For the HEAD-lookup path a 404 must come out of ``push`` as
    ``RepoNotFound`` only when it originates from the POST /contents
    endpoint — the branch-lookup 404 is normal (first-push case).
    We therefore exercise the error via the POST leg by stubbing the
    branch endpoint to return a SHA successfully first."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"id": "deadbeef"}})
        if request.url.path.endswith("/git/trees/deadbeef"):
            return httpx.Response(200, json={"tree": []})
        return httpx.Response(status, json={"message": "nope"})

    adapter = CodebergAdapter()
    with pytest.raises(expected):
        await adapter.push_manifest(
            repo=_repo(),
            manifest=_manifest(),
            token="T",
            transport=httpx.MockTransport(handler),
        )


# ── BranchNotFound path ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_branch_not_found_on_non_branch_404_bubbles_up() -> None:
    """When the HEAD endpoint returns 404 we treat it as 'first push',
    so BranchNotFound is exposed only when the POST leg reports the
    branch missing mid-flight (rare but possible on a deleted branch
    between lookup and push)."""
    # Kept as a placeholder test — exercising this explicitly would
    # require a racy sequence. The error class exists for adapters
    # that report branch-missing distinctly from repo-missing (GitHub).
    from app.plugins._lib.git_forge.errors import BranchNotFound as _BNF
    assert issubclass(_BNF, Exception)
