"""InternetArchiveClient tests backed by httpx.MockTransport — no network."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.internet_archive.service import (
    IAError,
    InternetArchiveClient,
)


def _client(handler: httpx.MockTransport) -> InternetArchiveClient:
    return InternetArchiveClient(
        access_key="ak",
        secret_key="sk",
        transport=handler,
    )


# ── submit ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_posts_form_and_parses_job_id() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = request.content
        return httpx.Response(
            200,
            json={"url": "https://edition.example.org/browse/x", "job_id": "spn2-abc123"},
        )

    c = _client(httpx.MockTransport(handler))
    result = await c.submit("https://edition.example.org/browse/x")
    assert captured["method"] == "POST"
    assert captured["url"] == "https://web.archive.org/save/"
    assert captured["auth"] == "LOW ak:sk"
    # Request body is form-encoded (application/x-www-form-urlencoded).
    assert b"url=https" in (captured["body"] or b"")  # type: ignore[operator]
    assert b"capture_all=1" in (captured["body"] or b"")  # type: ignore[operator]
    assert result.job_id == "spn2-abc123"
    assert result.url == "https://edition.example.org/browse/x"


@pytest.mark.asyncio
async def test_submit_401_raises_iaerror() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    with pytest.raises(IAError) as excinfo:
        await _client(httpx.MockTransport(handler)).submit("https://x")
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_submit_without_keys_rejected_at_construction() -> None:
    with pytest.raises(IAError):
        InternetArchiveClient(access_key="", secret_key="sk")
    with pytest.raises(IAError):
        InternetArchiveClient(access_key="ak", secret_key="")


@pytest.mark.asyncio
async def test_submit_missing_job_id_in_response_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": "https://x"})  # no job_id

    with pytest.raises(IAError):
        await _client(httpx.MockTransport(handler)).submit("https://x")


# ── status ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_success_returns_wayback_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/save/status/spn2-abc"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "job_id": "spn2-abc",
                "original_url": "https://edition.example.org/browse/x",
                "timestamp": "20260423120000",
                "duration_sec": 12.5,
            },
        )

    c = _client(httpx.MockTransport(handler))
    result = await c.status("spn2-abc")
    assert result.status == "success"
    assert result.timestamp == "20260423120000"
    assert (
        result.wayback_url
        == "https://web.archive.org/web/20260423120000/https://edition.example.org/browse/x"
    )


@pytest.mark.asyncio
async def test_status_pending_returns_pending() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "pending", "job_id": "spn2-abc"})

    result = await _client(httpx.MockTransport(handler)).status("spn2-abc")
    assert result.status == "pending"
    assert result.wayback_url is None


@pytest.mark.asyncio
async def test_status_error_collapses_to_failed_with_message() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "error",
                "status_ext": "error:blocked",
                "message": "The server rejected the request",
                "job_id": "spn2-abc",
            },
        )

    result = await _client(httpx.MockTransport(handler)).status("spn2-abc")
    assert result.status == "failed"
    assert result.wayback_url is None
    assert "rejected" in (result.error or "")


@pytest.mark.asyncio
async def test_status_success_with_malformed_payload_degrades_to_failed() -> None:
    """SPN2 lists status=success but omits timestamp — we must not
    fabricate a Wayback URL."""
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "job_id": "spn2-abc"})

    result = await _client(httpx.MockTransport(handler)).status("spn2-abc")
    assert result.status == "failed"
    assert result.wayback_url is None


@pytest.mark.asyncio
async def test_status_http_429_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limit"})

    with pytest.raises(IAError) as excinfo:
        await _client(httpx.MockTransport(handler)).status("spn2-abc")
    assert excinfo.value.status_code == 429
