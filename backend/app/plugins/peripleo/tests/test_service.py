"""Peripleo search service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.peripleo.service import search


def _roma_hit() -> dict[str, object]:
    return {
        "identifier": "https://pleiades.stoa.org/places/423025",
        "title": "Roma",
        "description": "Roman settlement — capital of the Roman empire",
        "dataset": {"id": "pleiades", "title": "Pleiades"},
    }


def _idai_hit() -> dict[str, object]:
    return {
        "identifier": "https://gazetteer.dainst.org/place/2181131",
        "title": "Ostia Antica",
        "description": "Ancient harbour city",
        "dataset": {"id": "idai", "title": "iDAI.gazetteer"},
    }


@pytest.mark.asyncio
async def test_search_parses_pleiades_hit() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"total": 1, "items": [_roma_hit()]})

    hits = await search("roma", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.uri == "https://pleiades.stoa.org/places/423025"
    assert hit.label == "Roma"
    assert hit.source == "Pleiades"
    assert "Roman empire" in hit.detail
    assert "peripleo.pelagios.org" in str(captured["url"])
    assert "q=roma" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_parses_idai_hit() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [_idai_hit()]})

    hits = await search("ostia", transport=httpx.MockTransport(handler))
    assert hits[0].source == "iDAI.gazetteer"


@pytest.mark.asyncio
async def test_search_infers_source_from_uri_when_dataset_missing() -> None:
    row = {
        "identifier": "https://pleiades.stoa.org/places/999",
        "title": "Some place",
        # no dataset field
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [row]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits[0].source == "Pleiades"


@pytest.mark.asyncio
async def test_search_accepts_legacy_id_field() -> None:
    """Older Peripleo versions used "id" rather than "identifier"."""
    row = {
        "id": "https://pleiades.stoa.org/places/423025",
        "title": "Roma",
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [row]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].uri == "https://pleiades.stoa.org/places/423025"


@pytest.mark.asyncio
async def test_search_accepts_legacy_hits_envelope() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": [_roma_hit()]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {
                "identifier": f"https://pleiades.stoa.org/places/{1000 + i}",
                "title": f"Place {i}",
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"items": items})

    hits = await search("x", rows=5, transport=httpx.MockTransport(handler))
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_skips_rows_without_identifier() -> None:
    broken = [
        {"title": "No id"},
        {"identifier": "not-a-url", "title": "Bad uri"},
        _roma_hit(),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": broken})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].label == "Roma"


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []
