"""Tests for the native Webhook Dispatcher plugin.

Split into two groups:

- Router CRUD (Admin-only; non-admin should get 403). SSRF check is
  disabled via monkeypatch so we can use test-friendly hostnames that
  do not hit DNS.
- Delivery service unit tests (mock httpx.AsyncClient). Cover HMAC
  signing, absence of signature when no secret, and the retry-on-
  transient-error behaviour.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.plugins._native.webhook_dispatcher import service as webhook_service
from app.plugins._native.webhook_dispatcher.models import WebhookEndpoint
from app.plugins._native.webhook_dispatcher.schemas import SUPPORTED_EVENTS
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)

_PUBLIC_URL = "https://webhook.example.com/ingest"


# ── Auth helpers ─────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def no_ssrf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short-circuit SSRF check so test hostnames don't hit DNS.

    The webhook router's Pydantic schemas call check_ssrf on `url`;
    patching its import site lets us use example.com without actually
    resolving a public address.
    """
    monkeypatch.setattr(
        "app.plugins._native.webhook_dispatcher.schemas.check_ssrf",
        lambda _url: None,
    )


@pytest_asyncio.fixture
async def endpoint(db_session: AsyncSession) -> WebhookEndpoint:
    ep = WebhookEndpoint(
        label="ingest",
        url=_PUBLIC_URL,
        events=["collection.published"],
        secret="s3cr3t",
        active=True,
    )
    db_session.add(ep)
    await db_session.flush()
    await db_session.refresh(ep)
    return ep


# ── Router — events listing ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_events_as_admin(
    client: AsyncClient, seeded_admin: object,
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.get("/api/v1/webhooks/events", headers=_auth(token))
    assert res.status_code == 200
    assert set(res.json()["data"]) == set(SUPPORTED_EVENTS)


@pytest.mark.asyncio
async def test_list_events_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: object,
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/webhooks/events", headers=_auth(token))
    assert res.status_code == 403


# ── Router — CRUD ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_webhook_happy_path(
    client: AsyncClient, seeded_admin: object,
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/webhooks",
        json={
            "label": "Deposit hook",
            "url": _PUBLIC_URL,
            "events": ["collection.published"],
            "secret": "shh",
        },
        headers=_auth(token),
    )
    assert res.status_code == 201
    body = res.json()["data"]
    assert body["label"] == "Deposit hook"
    assert body["events"] == ["collection.published"]
    # secret never leaks; only a boolean marker.
    assert body["secret_set"] is True
    assert "secret" not in body


@pytest.mark.asyncio
async def test_create_webhook_rejects_unknown_event(
    client: AsyncClient, seeded_admin: object,
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.post(
        "/api/v1/webhooks",
        json={
            "label": "Bogus",
            "url": _PUBLIC_URL,
            "events": ["not.a.real.event"],
        },
        headers=_auth(token),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_create_webhook_as_non_admin_returns_403(
    client: AsyncClient, seeded_user: object,
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        "/api/v1/webhooks",
        json={
            "label": "denied",
            "url": _PUBLIC_URL,
            "events": ["collection.published"],
        },
        headers=_auth(token),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_list_update_delete_flow(
    client: AsyncClient,
    seeded_admin: object,
    endpoint: WebhookEndpoint,
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)

    # List
    res = await client.get("/api/v1/webhooks", headers=_auth(token))
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 1
    assert rows[0]["label"] == "ingest"

    # Update label
    res = await client.put(
        f"/api/v1/webhooks/{endpoint.id}",
        json={"label": "ingest-v2"},
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["label"] == "ingest-v2"

    # Delete
    res = await client.delete(
        f"/api/v1/webhooks/{endpoint.id}",
        headers=_auth(token),
    )
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_update_nonexistent_returns_404(
    client: AsyncClient, seeded_admin: object,
) -> None:
    token = await _login_as(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    res = await client.put(
        "/api/v1/webhooks/00000000-0000-0000-0000-000000000000",
        json={"label": "ghost"},
        headers=_auth(token),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_as_non_admin_returns_403(
    client: AsyncClient,
    seeded_user: object,
    endpoint: WebhookEndpoint,
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.delete(
        f"/api/v1/webhooks/{endpoint.id}",
        headers=_auth(token),
    )
    assert res.status_code == 403


# ── Service — HMAC signing and retry behaviour ───────────────────────────────


def test_build_headers_includes_hmac_when_secret_set() -> None:
    ep = WebhookEndpoint(
        label="x",
        url=_PUBLIC_URL,
        events=["collection.published"],
        secret="my-secret",
        active=True,
    )
    body = '{"hello":"world"}'
    headers = webhook_service._build_headers(ep, body, "collection.published")
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Aracne-Event"] == "collection.published"
    expected_sig = hmac.new(b"my-secret", body.encode(), hashlib.sha256).hexdigest()
    assert headers["X-Aracne-Signature"] == f"sha256={expected_sig}"


def test_build_headers_omits_signature_when_secret_absent() -> None:
    ep = WebhookEndpoint(
        label="x", url=_PUBLIC_URL, events=["collection.published"],
        secret=None, active=True,
    )
    headers = webhook_service._build_headers(ep, "body", "collection.published")
    assert "X-Aracne-Signature" not in headers


@pytest.mark.asyncio
async def test_dispatch_event_skips_unknown_event(
    db_session: AsyncSession, endpoint: WebhookEndpoint,
) -> None:
    """An unknown event name is silently dropped — no raise, no HTTP call."""
    with patch(
        "app.plugins._native.webhook_dispatcher.service._deliver",
        new=AsyncMock(),
    ) as mock_deliver:
        await webhook_service.dispatch_event(
            db_session, "not.a.real.event", {"x": 1},
        )
        mock_deliver.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_event_only_reaches_subscribed_active_endpoints(
    db_session: AsyncSession,
) -> None:
    # Two endpoints:
    #   - ep_a: subscribed + active → should receive.
    #   - ep_b: subscribed but inactive → should be skipped.
    #   - ep_c: active but subscribed to a different event → should be skipped.
    for label, events, active in (
        ("ep_a", ["collection.published"], True),
        ("ep_b", ["collection.published"], False),
        ("ep_c", ["document.uploaded"], True),
    ):
        db_session.add(
            WebhookEndpoint(
                label=label, url=_PUBLIC_URL,
                events=events, active=active, secret=None,
            )
        )
    await db_session.flush()

    delivered: list[str] = []

    async def _fake_deliver(
        db: AsyncSession, ep: WebhookEndpoint, event: str, payload: dict[str, Any],
    ) -> None:
        delivered.append(ep.label)

    with patch(
        "app.plugins._native.webhook_dispatcher.service._deliver",
        new=_fake_deliver,
    ):
        await webhook_service.dispatch_event(
            db_session, "collection.published", {"x": 1},
        )

    assert delivered == ["ep_a"]


@pytest.mark.asyncio
async def test_deliver_retries_on_transient_error_then_succeeds(
    db_session: AsyncSession, endpoint: WebhookEndpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient network error on the first attempt, then success."""
    # Collapse exponential backoff so the test is fast.
    monkeypatch.setattr(webhook_service, "_BACKOFF_BASE", 0)

    calls = {"n": 0}

    async def _fake_once(url: str, body: str, headers: dict[str, str]) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("transient")
        return 200

    monkeypatch.setattr(webhook_service, "_deliver_once", _fake_once)

    await webhook_service._deliver(
        db_session, endpoint, "collection.published", {"x": 1},
    )
    assert calls["n"] == 2
    # Endpoint row now reflects the successful outcome.
    assert endpoint.last_status_code == 200
    assert endpoint.last_error is None


@pytest.mark.asyncio
async def test_deliver_records_4xx_without_retry(
    db_session: AsyncSession, endpoint: WebhookEndpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 4xx error is deterministic — record and stop retrying."""
    monkeypatch.setattr(webhook_service, "_BACKOFF_BASE", 0)
    calls = {"n": 0}

    async def _fake_once(url: str, body: str, headers: dict[str, str]) -> int:
        calls["n"] += 1
        raise httpx.HTTPStatusError(
            "bad req",
            request=httpx.Request("POST", url),
            response=httpx.Response(400),
        )

    monkeypatch.setattr(webhook_service, "_deliver_once", _fake_once)

    await webhook_service._deliver(
        db_session, endpoint, "collection.published", {"x": 1},
    )
    assert calls["n"] == 1  # no retry on 4xx
    assert endpoint.last_status_code == 400
    assert endpoint.last_error == "HTTP 400"
