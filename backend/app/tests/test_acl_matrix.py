"""ACL negative-path matrix — one 403 assertion per role-protected endpoint.

Rationale: each endpoint that declares ``Depends(require_role(min_role=...))``
must pair its happy-path test (already present in the per-router test
file) with a negative-path test that confirms an under-privileged role
gets **403 FORBIDDEN**. This file is the consolidated below-role
regression net — whenever a new protected endpoint is added, adding a
row here is the canonical place to prove it is gated.

The ACL guard runs *before* the endpoint handler, so bogus IDs and
empty bodies are fine: we never reach the handler. We therefore do not
seed any domain data — just the user + role rows. For every case, the
only acceptable status code is 403.

Coverage scope: endpoints whose routers are mounted in conftest.py.
That includes all app.routers.* and the plugin routers explicitly
wired into the test app (backup, collections, evt, named_entities,
oai_pmh, webhook_dispatcher). ``ai`` routes live under an un-wired
router and are intentionally skipped here.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import pytest
from httpx import AsyncClient

from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    DESIGNER_PASSWORD,
    DESIGNER_USERNAME,
    EIC_PASSWORD,
    EIC_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200, f"login for {username} failed"
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Fake IDs that the handler would dereference, but the ACL guard fires
# first so no DB lookup actually happens.
_FAKE_UUID = str(uuid.UUID(int=0))
_FAKE_SLUG = "no-such-collection"
_FAKE_FILE = "no-such-doc.xml"

Role = Literal["user", "editor", "designer", "eic"]
Method = Literal["GET", "POST", "PATCH", "PUT", "DELETE"]


def _credentials(role: Role) -> tuple[str, str]:
    match role:
        case "user" | "editor":
            return TEST_USER_USERNAME, TEST_USER_PASSWORD
        case "designer":
            return DESIGNER_USERNAME, DESIGNER_PASSWORD
        case "eic":
            return EIC_USERNAME, EIC_PASSWORD


# ── Matrix of (role, method, path) triples expected to produce 403 ───────────
#
# Each entry: (below_role, HTTP method, URL path). The `below_role` is
# one strictly below the endpoint's min_role. We also run each case
# anonymously (no token) and assert the result is one of {401, 403}.

ACL_CASES: list[tuple[Role, Method, str]] = [
    # ── app/routers/users.py (EditorInChief / Admin) ────────────────────────
    ("editor", "GET",    "/api/v1/users"),                         # EiC+
    ("editor", "POST",   "/api/v1/users"),                         # Admin (EiC also 403 on create? check — EiC+ wrapper, but create is Admin)
    ("editor", "GET",    f"/api/v1/users/{_FAKE_UUID}"),           # EiC+
    ("editor", "PATCH",  f"/api/v1/users/{_FAKE_UUID}"),           # Admin
    ("editor", "DELETE", f"/api/v1/users/{_FAKE_UUID}"),           # Admin
    ("editor", "POST",   f"/api/v1/users/{_FAKE_UUID}/roles"),     # Admin
    ("editor", "DELETE", f"/api/v1/users/{_FAKE_UUID}/roles/Admin"),  # Admin

    # ── app/routers/body_templates.py (Admin) ───────────────────────────────
    ("editor", "POST",   "/api/v1/body-templates"),
    ("editor", "PATCH",  f"/api/v1/body-templates/{_FAKE_UUID}"),
    ("editor", "DELETE", f"/api/v1/body-templates/{_FAKE_UUID}"),

    # ── app/routers/licenses.py (Admin) ─────────────────────────────────────
    ("editor", "POST",   "/api/v1/licenses"),
    ("editor", "PATCH",  f"/api/v1/licenses/{_FAKE_UUID}"),
    ("editor", "DELETE", f"/api/v1/licenses/{_FAKE_UUID}"),

    # ── app/routers/schemas.py — mutations only (EditorInChief)
    # GET /schemas and GET /schemas/{id}/cm5-file are [auth], open to
    # any authenticated user (the document editor reads the CM5 file
    # to drive its schema-aware autocomplete).
    ("editor", "POST",   "/api/v1/schemas"),
    ("editor", "DELETE", f"/api/v1/schemas/{_FAKE_UUID}"),
    ("editor", "POST",   f"/api/v1/schemas/{_FAKE_UUID}/upload-validation"),
    ("editor", "POST",   f"/api/v1/schemas/{_FAKE_UUID}/upload-cm5"),
    ("editor", "POST",   f"/api/v1/schemas/{_FAKE_UUID}/generate-cm5"),

    # ── app/routers/settings.py (Admin) ─────────────────────────────────────
    ("editor", "GET",    "/api/v1/settings"),
    ("editor", "GET",    "/api/v1/settings/platform_name"),
    ("editor", "PATCH",  "/api/v1/settings/platform_name"),
    ("editor", "POST",   "/api/v1/settings/logo"),
    ("editor", "POST",   "/api/v1/settings/homepage-css"),
    ("editor", "DELETE", "/api/v1/settings/homepage-css"),

    # ── app/routers/plugins.py (Admin) ──────────────────────────────────────
    ("editor", "GET",    "/api/v1/plugins"),
    ("editor", "POST",   "/api/v1/plugins/help/activate"),
    ("editor", "POST",   "/api/v1/plugins/help/deactivate"),
    ("editor", "DELETE", "/api/v1/plugins/help"),

    # ── app/routers/auth.py — impersonate (Admin) ───────────────────────────
    ("editor", "POST",   f"/api/v1/auth/impersonate/{_FAKE_UUID}"),

    # ── plugins/_native/backup (Admin) ──────────────────────────────────────
    ("editor", "POST",   "/api/v1/backup/jobs"),
    ("editor", "GET",    "/api/v1/backup/jobs"),
    ("editor", "GET",    f"/api/v1/backup/jobs/{_FAKE_UUID}"),
    ("editor", "GET",    f"/api/v1/backup/jobs/{_FAKE_UUID}/download"),
    ("editor", "DELETE", f"/api/v1/backup/jobs/{_FAKE_UUID}"),

    # ── plugins/_native/webhook_dispatcher (Admin) ──────────────────────────
    ("editor", "GET",    "/api/v1/webhooks/events"),
    ("editor", "GET",    "/api/v1/webhooks"),
    ("editor", "POST",   "/api/v1/webhooks"),
    ("editor", "PUT",    f"/api/v1/webhooks/{_FAKE_UUID}"),
    ("editor", "DELETE", f"/api/v1/webhooks/{_FAKE_UUID}"),
    ("editor", "POST",   f"/api/v1/webhooks/{_FAKE_UUID}/test"),
]


# ── Parametrised negative-path tests ─────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "method", "path"),
    ACL_CASES,
    ids=[f"{m} {p}" for _, m, p in ACL_CASES],
)
async def test_below_role_returns_403(
    client: AsyncClient,
    seeded_user: object,       # Editor
    seeded_designer: object,   # Designer (same level as Editor — used for some EiC endpoints)
    role: Role,
    method: Method,
    path: str,
) -> None:
    """Authenticated user below the endpoint's min_role → 403."""
    username, password = _credentials(role)
    token = await _login_as(client, username, password)

    kwargs: dict[str, Any] = {"headers": _auth(token)}
    # For methods that expect a body, send an empty/minimal one — the
    # ACL guard still runs before the body is parsed.
    if method in ("POST", "PATCH", "PUT"):
        kwargs["json"] = {}

    req = getattr(client, method.lower())
    res = await req(path, **kwargs)
    assert res.status_code == 403, (
        f"{method} {path} with role={role}: expected 403, got {res.status_code} "
        f"({res.text[:120]})"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [(m, p) for _, m, p in ACL_CASES],
    ids=[f"{m} {p}" for _, m, p in ACL_CASES],
)
async def test_anonymous_access_returns_401(
    client: AsyncClient,
    method: Method,
    path: str,
) -> None:
    """No credentials → 401 (never 200 / 2xx, never a silent pass-through)."""
    kwargs: dict[str, Any] = {}
    if method in ("POST", "PATCH", "PUT"):
        kwargs["json"] = {}
    req = getattr(client, method.lower())
    res = await req(path, **kwargs)
    # 401 is the usual outcome for missing Bearer; 403 is acceptable on
    # routers that treat missing auth as forbidden. Anything in 2xx is a bug.
    assert res.status_code in (401, 403), (
        f"{method} {path} anonymously: expected 401/403, got {res.status_code} "
        f"({res.text[:120]})"
    )


# ── Positive cross-check: a single happy-path confirms the matrix is
# not trivially passing because all endpoints 403 everyone. We do not
# exercise domain logic — we just prove that `admin` *can* list plugins
# (which is Admin-gated and on the list above). If this test passes
# together with the matrix above, we know the distinction admin-vs-
# editor is genuinely enforced.


@pytest.mark.asyncio
async def test_admin_can_access_admin_endpoint_sanity_check(
    client: AsyncClient,
    seeded_admin: object,
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/plugins", headers=_auth(token))
    assert res.status_code == 200
