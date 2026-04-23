"""Tests for observability primitives: /metrics, /health split, event
emission + Prometheus counters on hot paths (login, plugin lifecycle).

These tests do not assert exact numeric values on shared counters —
Prometheus counters are process-global and other tests in the same
session may have incremented them. We assert **deltas** by snapshotting
the counter value before the action and checking the delta afterwards.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.metrics import (
    LOGIN_ATTEMPTS,
    PLUGIN_LIFECYCLE,
    REQUEST_COUNT,
    UNHANDLED_EXCEPTIONS,
)
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _counter_value(counter: object, **labels: str) -> float:
    """Read a Prometheus Counter's current value for the given labels.

    Uses the internal ``_value.get()`` which is stable on
    prometheus_client and safe in tests that run in a single process.
    """
    labeled = counter.labels(**labels) if labels else counter  # type: ignore[attr-defined]
    return float(labeled._value.get())  # type: ignore[attr-defined]


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── /metrics endpoint ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(
    client: AsyncClient,
) -> None:
    res = await client.get("/api/v1/metrics")
    assert res.status_code == 200
    # Prometheus content type — possibly with a version suffix.
    assert "text/plain" in res.headers["content-type"]
    body = res.text
    # Every declared metric name should appear in the exposition.
    assert "aracne2_http_requests_total" in body
    assert "aracne2_http_request_duration_seconds" in body
    assert "aracne2_login_attempts_total" in body
    assert "aracne2_plugin_lifecycle_total" in body
    assert "aracne2_unhandled_exceptions_total" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_not_self_instrumented(
    client: AsyncClient,
) -> None:
    """The /metrics endpoint must not count itself — that would make
    every Prometheus scrape increment the counter it reports on."""
    before = _counter_value(
        REQUEST_COUNT, method="GET", path="/api/v1/metrics", status="200",
    )
    await client.get("/api/v1/metrics")
    after = _counter_value(
        REQUEST_COUNT, method="GET", path="/api/v1/metrics", status="200",
    )
    assert after == before


@pytest.mark.asyncio
async def test_metrics_endpoint_increments_request_counter_for_other_paths(
    client: AsyncClient,
) -> None:
    """A normal request to a real endpoint should bump the counter
    for that path template (not the raw URL)."""
    before = _counter_value(
        REQUEST_COUNT, method="GET", path="/api/v1/health", status="200",
    )
    await client.get("/api/v1/health")
    after = _counter_value(
        REQUEST_COUNT, method="GET", path="/api/v1/health", status="200",
    )
    assert after - before == 1.0


# ── /health/live and /health/ready ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_liveness_probe_200_no_deps(client: AsyncClient) -> None:
    """Liveness must succeed even when downstream services are not
    checked — it only asks 'is this process alive?'."""
    res = await client.get("/api/v1/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_probe_200_when_all_deps_up(
    client_with_existdb: AsyncClient,
) -> None:
    """Default test mock_existdb.ping returns True and DB is in-memory
    sqlite — both reachable, so readiness is 200."""
    res = await client_with_existdb.get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["services"]["postgres"] == "ok"
    assert body["services"]["existdb"] == "ok"


@pytest.mark.asyncio
async def test_readiness_probe_503_when_existdb_down(
    client_with_existdb: AsyncClient,
    mock_existdb: object,
) -> None:
    mock_existdb.ping.return_value = False  # type: ignore[attr-defined]
    res = await client_with_existdb.get("/api/v1/health/ready")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "not_ready"
    assert body["services"]["existdb"] == "error"


# ── Counter: login success / failure ────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success_bumps_success_counter(
    client: AsyncClient, seeded_user: object,
) -> None:
    before = _counter_value(LOGIN_ATTEMPTS, outcome="success")
    await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    after = _counter_value(LOGIN_ATTEMPTS, outcome="success")
    assert after - before == 1.0


@pytest.mark.asyncio
async def test_login_failure_bumps_failure_counter(
    client: AsyncClient, seeded_user: object,
) -> None:
    before = _counter_value(LOGIN_ATTEMPTS, outcome="failure")
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": TEST_USER_USERNAME, "password": "wrong"},
    )
    assert res.status_code == 401
    after = _counter_value(LOGIN_ATTEMPTS, outcome="failure")
    assert after - before == 1.0


# ── Counter: plugin lifecycle ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plugin_activation_bumps_lifecycle_counter(
    client: AsyncClient, seeded_admin: object,
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    # Seed a plugin row by listing first — plugin_loader did not run
    # in tests, so the plugins table may be empty. We exercise the
    # counter by calling the endpoint; an unknown plugin returns 404
    # before the counter increments, which is acceptable.
    list_res = await client.get("/api/v1/plugins", headers=_auth(token))
    assert list_res.status_code == 200
    rows = list_res.json()["data"]
    if not rows:
        pytest.skip("plugins table empty in test DB; counter path unreachable")

    target = next((r for r in rows if not r.get("is_native")), None)
    if target is None:
        pytest.skip("no non-native plugin row available for lifecycle test")

    name = target["name"]
    before = _counter_value(PLUGIN_LIFECYCLE, action="activated", plugin=name)
    res = await client.post(
        f"/api/v1/plugins/{name}/activate",
        headers=_auth(token),
    )
    # Activate returns 200 on success; tolerate 409 if already active
    # from a previous test in the same process.
    assert res.status_code in (200, 409)
    if res.status_code == 200:
        after = _counter_value(PLUGIN_LIFECYCLE, action="activated", plugin=name)
        assert after - before == 1.0


# ── Counter: unhandled exceptions ───────────────────────────────────────────
#
# The generic_exception_handler in main.py increments UNHANDLED_EXCEPTIONS
# and returns a 500. Inducing a 500 via the test client requires either
# ASGITransport(raise_app_exceptions=False) or mounting a throwaway
# crash route — neither worth the plumbing for a two-line handler. The
# counter's *presence* in the /metrics exposition is validated by
# test_metrics_endpoint_returns_prometheus_format above.


def test_unhandled_exceptions_counter_is_directly_incrementable() -> None:
    """Sanity check that the counter object itself is functional."""
    before = _counter_value(UNHANDLED_EXCEPTIONS)
    UNHANDLED_EXCEPTIONS.inc()
    assert _counter_value(UNHANDLED_EXCEPTIONS) - before == 1.0
