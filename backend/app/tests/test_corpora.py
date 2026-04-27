"""Corpus REST API + MCP plugin auth/tools — happy paths and ACL.

The corpus is the platform primitive that scopes a programmatic-access
token to a subset of collections. Test coverage is split in three:

* Corpus CRUD via ``/api/v1/corpora`` — admin only, validation at the
  edges (duplicate name, unknown collection id).
* MCP token issuance via ``/api/v1/corpora/{id}/tokens`` — verify the
  plaintext + Claude Desktop snippet are returned exactly once at
  creation, the listing endpoint never echoes the plaintext.
* MCP plugin endpoint at ``/api/v1/mcp`` — auth (401 paths) and one
  tool happy-path (`list_collections` returning corpus-scoped rows).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_USER_PASSWORD, TEST_USER_USERNAME


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def public_collection(db_session: AsyncSession) -> Collection:
    """A published, publicly visible collection eligible for corpus membership."""
    c = Collection(
        slug="hamlet-folio",
        title="Hamlet (First Folio)",
        description="Tragedy by William Shakespeare.",
        status=CollectionStatus.published,
        is_public=True,
        published_at=datetime.now(UTC),
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def out_of_scope_collection(db_session: AsyncSession) -> Collection:
    """A second public+published collection that *no* corpus owns by default —
    used to confirm scope filters never leak across corpora."""
    c = Collection(
        slug="cancelleria-aragonese",
        title="Cancelleria Aragonese",
        description="Medieval royal chancery.",
        status=CollectionStatus.published,
        is_public=True,
        published_at=datetime.now(UTC),
    )
    db_session.add(c)
    await db_session.flush()
    return c


# ── Corpus CRUD ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_corpus_as_admin(
    client: AsyncClient,
    seeded_admin: User,
    public_collection: Collection,
) -> None:
    """Admin creates a corpus with one collection and the list reflects it."""
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/corpora",
        json={
            "name": "Shakespeare",
            "description": "Drammi shakespeariani 2026",
            "collection_ids": [str(public_collection.id)],
        },
        headers=_bearer(token),
    )
    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["name"] == "Shakespeare"
    assert body["token_count"] == 0
    assert len(body["collections"]) == 1
    assert body["collections"][0]["slug"] == "hamlet-folio"

    # And the list endpoint sees it.
    res2 = await client.get("/api/v1/corpora", headers=_bearer(token))
    assert res2.status_code == 200
    names = [c["name"] for c in res2.json()["data"]]
    assert "Shakespeare" in names


@pytest.mark.asyncio
async def test_corpus_endpoints_forbid_non_admin(
    client: AsyncClient,
    seeded_user: User,
) -> None:
    """Editor / User accounts get 403 on every corpus endpoint."""
    token = await _login(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    for path in [
        ("GET", "/api/v1/corpora"),
        ("POST", "/api/v1/corpora"),
    ]:
        method, url = path
        res = await client.request(method, url, headers=_bearer(token), json={})
        assert res.status_code == 403, f"{method} {url} expected 403, got {res.status_code}"


@pytest.mark.asyncio
async def test_create_corpus_rejects_unknown_collection_id(
    client: AsyncClient,
    seeded_admin: User,
) -> None:
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/corpora",
        json={
            "name": "Mistakes",
            "description": None,
            "collection_ids": ["00000000-0000-0000-0000-000000000000"],
        },
        headers=_bearer(token),
    )
    # DomainValidationError → 422 (platform-wide convention).
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "UNKNOWN_COLLECTION"


@pytest.mark.asyncio
async def test_create_corpus_rejects_duplicate_name(
    client: AsyncClient,
    seeded_admin: User,
) -> None:
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    payload = {"name": "Shakespeare", "description": None, "collection_ids": []}
    r1 = await client.post("/api/v1/corpora", json=payload, headers=_bearer(token))
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/corpora", json=payload, headers=_bearer(token))
    # DomainValidationError → 422 (platform-wide convention).
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "DUPLICATE_NAME"


# ── MCP token issuance ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_token_returns_plaintext_once(
    client: AsyncClient,
    seeded_admin: User,
    public_collection: Collection,
) -> None:
    """The create endpoint returns a one-time plaintext + a Claude Desktop
    snippet. The list endpoint never echoes the plaintext."""
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    create = await client.post(
        "/api/v1/corpora",
        json={
            "name": "Shakespeare",
            "description": None,
            "collection_ids": [str(public_collection.id)],
        },
        headers=_bearer(token),
    )
    corpus_id = create.json()["data"]["id"]

    issue = await client.post(
        f"/api/v1/corpora/{corpus_id}/tokens",
        json={"label": "Alice — laptop"},
        headers=_bearer(token),
    )
    assert issue.status_code == 201
    body = issue.json()["data"]
    assert body["plaintext"].startswith("aracne2_mcp_")
    assert "claude_desktop_snippet" in body
    assert "/api/v1/mcp" in body["claude_desktop_snippet"]
    assert body["plaintext"] in body["claude_desktop_snippet"]

    listed = await client.get(
        f"/api/v1/corpora/{corpus_id}/tokens", headers=_bearer(token)
    )
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert len(rows) == 1
    # The list response carries no plaintext.
    assert "plaintext" not in rows[0]
    assert "claude_desktop_snippet" not in rows[0]
    assert rows[0]["label"] == "Alice — laptop"
    assert rows[0]["revoked_at"] is None


@pytest.mark.asyncio
async def test_revoke_token_marks_revoked_at(
    client: AsyncClient,
    seeded_admin: User,
    public_collection: Collection,
) -> None:
    token = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    create = await client.post(
        "/api/v1/corpora",
        json={"name": "S", "description": None, "collection_ids": []},
        headers=_bearer(token),
    )
    corpus_id = create.json()["data"]["id"]
    issue = await client.post(
        f"/api/v1/corpora/{corpus_id}/tokens",
        json={"label": "x"},
        headers=_bearer(token),
    )
    token_id = issue.json()["data"]["id"]
    revoke = await client.delete(
        f"/api/v1/corpora/{corpus_id}/tokens/{token_id}",
        headers=_bearer(token),
    )
    assert revoke.status_code == 204

    listed = await client.get(
        f"/api/v1/corpora/{corpus_id}/tokens", headers=_bearer(token)
    )
    rows = listed.json()["data"]
    assert rows[0]["revoked_at"] is not None


# ── MCP plugin auth + tool happy path ─────────────────────────────────────────


@pytest_asyncio.fixture
async def issued_token(
    client: AsyncClient,
    seeded_admin: User,
    public_collection: Collection,
    out_of_scope_collection: Collection,
) -> str:
    """Issue a token scoped to ``public_collection`` only, then return its plaintext."""
    admin_jwt = await _login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    create = await client.post(
        "/api/v1/corpora",
        json={
            "name": "Shakespeare-only",
            "description": None,
            "collection_ids": [str(public_collection.id)],
        },
        headers=_bearer(admin_jwt),
    )
    corpus_id = create.json()["data"]["id"]
    issue = await client.post(
        f"/api/v1/corpora/{corpus_id}/tokens",
        json={"label": "test"},
        headers=_bearer(admin_jwt),
    )
    return str(issue.json()["data"]["plaintext"])


@pytest.mark.asyncio
async def test_mcp_endpoint_rejects_missing_authorization(
    client: AsyncClient,
) -> None:
    """No Authorization header → 401 with JSON-RPC -32001."""
    # Mount the MCP router for tests — production mounts via plugin loader,
    # tests need a manual hook because the loader doesn't run under pytest.
    from app.main import app
    from app.plugins.mcp_server.router import router as mcp_router

    if not any(getattr(r, "path", "").startswith("/api/v1/mcp") for r in app.routes):
        app.include_router(mcp_router, prefix="/api/v1")

    res = await client.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == -32001


@pytest.mark.asyncio
async def test_mcp_endpoint_rejects_bad_token(
    client: AsyncClient,
) -> None:
    from app.main import app
    from app.plugins.mcp_server.router import router as mcp_router

    if not any(getattr(r, "path", "").startswith("/api/v1/mcp") for r in app.routes):
        app.include_router(mcp_router, prefix="/api/v1")

    res = await client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers=_bearer("aracne2_mcp_completely-wrong-token"),
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_mcp_initialize_and_tools_list(
    client: AsyncClient,
    issued_token: str,
) -> None:
    """The token authenticates, initialize returns server info, tools/list
    advertises the read tools, and tools/call list_collections returns rows
    only for the corpus the token was issued for."""
    from app.main import app
    from app.plugins.mcp_server.router import router as mcp_router

    if not any(getattr(r, "path", "").startswith("/api/v1/mcp") for r in app.routes):
        app.include_router(mcp_router, prefix="/api/v1")

    h = _bearer(issued_token)
    init = await client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers=h,
    )
    assert init.status_code == 200, init.text
    body = init.json()
    assert body["result"]["serverInfo"]["name"] == "aracne2"

    tools = await client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers=h,
    )
    assert tools.status_code == 200
    tool_names = {t["name"] for t in tools.json()["result"]["tools"]}
    assert {
        "list_collections",
        "get_collection",
        "list_documents",
        "get_document_source",
        "search_entities",
        "find_entity_occurrences",
    } <= tool_names

    call = await client.post(
        "/api/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_collections", "arguments": {}},
        },
        headers=h,
    )
    assert call.status_code == 200
    payload = call.json()["result"]
    assert payload["isError"] is False
    # The tool wraps its result in a single text-content block carrying JSON.
    import json as _json

    rows = _json.loads(payload["content"][0]["text"])
    slugs = {r["slug"] for r in rows}
    assert "hamlet-folio" in slugs
    # The out-of-scope collection is not in this token's corpus and must
    # not appear, even though it is public+published.
    assert "cancelleria-aragonese" not in slugs
