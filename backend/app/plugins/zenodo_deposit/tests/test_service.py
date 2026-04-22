"""ZenodoClient tests backed by httpx.MockTransport — no network.

Exercises the Zenodo (InvenioRDM) ``/api/records`` flow the client now
targets: create draft with metadata, init/upload/commit files, publish,
and the resource-type vocabulary fetch.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.plugins.zenodo_deposit.service import ZenodoClient, ZenodoError

BASE = "https://sandbox.zenodo.org"


def _client(handler: httpx.MockTransport) -> ZenodoClient:
    return ZenodoClient(base_url=BASE, api_token="secret-token", transport=handler)


# ── create_draft ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_draft_posts_metadata_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer secret-token"
        return httpx.Response(
            201,
            json={
                "id": "abc12-xy345",
                "links": {"self_html": "https://sandbox.zenodo.org/uploads/abc12-xy345"},
            },
        )

    c = _client(httpx.MockTransport(handler))
    payload = {"metadata": {"title": "X"}}
    draft = await c.create_draft(payload)
    assert captured["method"] == "POST"
    assert captured["url"] == f"{BASE}/api/records"
    assert captured["body"] == payload
    assert draft.id == "abc12-xy345"
    assert draft.record_url == "https://sandbox.zenodo.org/uploads/abc12-xy345"


# ── upload_file (init + stream + commit) ────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_file_performs_three_phase_flow() -> None:
    calls: list[tuple[str, str, bytes | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content if request.content else None
        calls.append((request.method, str(request.url), body))
        return httpx.Response(201 if request.method == "POST" else 200, json={"ok": True})

    c = _client(httpx.MockTransport(handler))
    await c.upload_file("abc12-xy345", "doc.xml", b"<tei/>")

    # Expected sequence: POST (init), PUT (content), POST (commit).
    methods = [m for m, _, _ in calls]
    urls = [u for _, u, _ in calls]
    assert methods == ["POST", "PUT", "POST"]
    assert urls[0] == f"{BASE}/api/records/abc12-xy345/draft/files"
    assert urls[1] == f"{BASE}/api/records/abc12-xy345/draft/files/doc.xml/content"
    assert urls[2] == f"{BASE}/api/records/abc12-xy345/draft/files/doc.xml/commit"
    # Init carried the filename in the body.
    init_body = json.loads(calls[0][2] or b"[]")
    assert init_body == [{"key": "doc.xml"}]
    # Content phase shipped the raw bytes.
    assert calls[1][2] == b"<tei/>"


# ── publish ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_doi_and_record_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/records/abc12-xy345/draft/actions/publish"
        return httpx.Response(
            202,
            json={
                "id": "abc12-xy345",
                "pids": {"doi": {"identifier": "10.5281/zenodo.42", "provider": "datacite"}},
                "links": {"self_html": "https://sandbox.zenodo.org/records/abc12-xy345"},
            },
        )

    c = _client(httpx.MockTransport(handler))
    result = await c.publish("abc12-xy345")
    assert result.doi == "10.5281/zenodo.42"
    assert result.record_url == "https://sandbox.zenodo.org/records/abc12-xy345"
    assert result.status == "published"


@pytest.mark.asyncio
async def test_publish_tolerates_missing_doi() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            202,
            json={"id": "abc12-xy345", "links": {"self_html": "https://x"}},
        )

    c = _client(httpx.MockTransport(handler))
    result = await c.publish("abc12-xy345")
    assert result.doi is None


# ── vocabulary fetch ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_resource_types_returns_hits_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/vocabularies/resourcetypes"
        return httpx.Response(
            200,
            json={
                "hits": {
                    "hits": [
                        {"id": "publication-book", "title": {"en": "Book"}},
                        {"id": "dataset", "title": {"en": "Dataset"}},
                    ],
                    "total": 2,
                }
            },
        )

    c = _client(httpx.MockTransport(handler))
    hits = await c.fetch_resource_types()
    assert len(hits) == 2
    assert hits[0]["id"] == "publication-book"


# ── error handling ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bad_token_raises_zenodo_error_with_401() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": 401, "message": "Unauthorized"})

    c = _client(httpx.MockTransport(handler))
    with pytest.raises(ZenodoError) as excinfo:
        await c.create_draft({})
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_5xx_retries_and_eventually_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"message": "Service unavailable"})

    async def instant_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(
        "app.plugins.zenodo_deposit.service.asyncio.sleep", instant_sleep
    )

    c = _client(httpx.MockTransport(handler))
    with pytest.raises(ZenodoError) as excinfo:
        await c.create_draft({})
    assert excinfo.value.status_code == 503
    assert calls["n"] == 3  # _MAX_RETRIES


@pytest.mark.asyncio
async def test_inveniordm_validation_errors_surface_in_message() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "status": 400,
                "message": "A validation error occurred.",
                "errors": [{"field": "metadata.title", "messages": ["Missing data"]}],
            },
        )

    c = _client(httpx.MockTransport(handler))
    with pytest.raises(ZenodoError) as excinfo:
        await c.create_draft({})
    assert "validation" in str(excinfo.value).lower()
    assert "metadata.title" in str(excinfo.value)


@pytest.mark.asyncio
async def test_empty_token_rejected_at_construction() -> None:
    with pytest.raises(ZenodoError):
        ZenodoClient(base_url=BASE, api_token="")
