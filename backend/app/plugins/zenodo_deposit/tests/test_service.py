"""ZenodoClient tests backed by httpx.MockTransport — no network."""

from __future__ import annotations

import json

import httpx
import pytest

from app.plugins.zenodo_deposit.service import ZenodoClient, ZenodoError

BASE = "https://sandbox.zenodo.org"


def _client(handler: httpx.MockTransport) -> ZenodoClient:
    return ZenodoClient(base_url=BASE, api_token="secret-token", transport=handler)


@pytest.mark.asyncio
async def test_create_draft_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/deposit/depositions"
        assert request.headers["Authorization"] == "Bearer secret-token"
        return httpx.Response(
            201,
            json={
                "id": 123,
                "links": {
                    "bucket": "https://sandbox.zenodo.org/api/files/abc",
                    "html": "https://sandbox.zenodo.org/deposit/123",
                },
            },
        )

    c = _client(httpx.MockTransport(handler))
    draft = await c.create_draft()
    assert draft.id == 123
    assert draft.bucket_url == "https://sandbox.zenodo.org/api/files/abc"
    assert draft.record_url == "https://sandbox.zenodo.org/deposit/123"


@pytest.mark.asyncio
async def test_upload_file_puts_to_bucket_url() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["content"] = request.content
        return httpx.Response(201, json={"ok": True})

    c = _client(httpx.MockTransport(handler))
    await c.upload_file("https://sandbox.zenodo.org/api/files/abc", "doc.xml", b"<tei/>")
    assert captured["method"] == "PUT"
    assert captured["url"] == "https://sandbox.zenodo.org/api/files/abc/doc.xml"
    assert captured["content"] == b"<tei/>"


@pytest.mark.asyncio
async def test_update_metadata_sends_json_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 123})

    c = _client(httpx.MockTransport(handler))
    payload = {"metadata": {"title": "X"}}
    await c.update_metadata(123, payload)
    assert captured["method"] == "PUT"
    assert str(captured["url"]) == f"{BASE}/api/deposit/depositions/123"
    assert captured["body"] == payload


@pytest.mark.asyncio
async def test_publish_returns_doi_and_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/deposit/depositions/123/actions/publish"
        return httpx.Response(
            202,
            json={
                "id": 123,
                "doi": "10.5281/zenodo.123",
                "links": {"html": "https://sandbox.zenodo.org/records/123"},
            },
        )

    c = _client(httpx.MockTransport(handler))
    result = await c.publish(123)
    assert result.doi == "10.5281/zenodo.123"
    assert result.record_url == "https://sandbox.zenodo.org/records/123"
    assert result.status == "published"


@pytest.mark.asyncio
async def test_bad_token_raises_zenodo_error_with_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": 401, "message": "Unauthorized"})

    c = _client(httpx.MockTransport(handler))
    with pytest.raises(ZenodoError) as excinfo:
        await c.create_draft()
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_5xx_retries_and_eventually_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"message": "Service unavailable"})

    # Short-circuit the backoff so the test runs in milliseconds.
    async def instant_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(
        "app.plugins.zenodo_deposit.service.asyncio.sleep", instant_sleep
    )

    c = _client(httpx.MockTransport(handler))
    with pytest.raises(ZenodoError) as excinfo:
        await c.create_draft()
    assert excinfo.value.status_code == 503
    assert calls["n"] == 3  # _MAX_RETRIES


@pytest.mark.asyncio
async def test_empty_token_rejected_at_construction() -> None:
    with pytest.raises(ZenodoError):
        ZenodoClient(base_url=BASE, api_token="")
