"""Wikidata search service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.wikidata.service import search


_DANTE_HIT: dict[str, object] = {
    "id": "Q1067",
    "title": "Q1067",
    "label": "Dante Alighieri",
    "description": "Italian poet, writer, and philosopher (c.1265–1321)",
    "concepturi": "http://www.wikidata.org/entity/Q1067",
    "url": "//www.wikidata.org/wiki/Q1067",
}


@pytest.mark.asyncio
async def test_search_parses_entity_hit() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"search": [_DANTE_HIT], "success": 1})

    hits = await search(
        "dante", lang="it", limit=10,
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.qid == "Q1067"
    assert hit.label == "Dante Alighieri"
    assert hit.uri == "http://www.wikidata.org/entity/Q1067"
    assert hit.description and "philosopher" in hit.description
    # The request went to the wbsearchentities action with our params.
    assert "wikidata.org/w/api.php" in str(captured["url"])
    assert "action=wbsearchentities" in str(captured["url"])
    assert "search=dante" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_passes_lang_and_limit_to_upstream() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"search": [], "success": 1})

    await search(
        "firenze", lang="en", limit=5,
        transport=httpx.MockTransport(handler),
    )
    url = str(captured["url"])
    assert "language=en" in url
    assert "limit=5" in url
    assert "type=item" in url


@pytest.mark.asyncio
async def test_search_skips_hits_missing_required_fields() -> None:
    """Wikidata occasionally returns hits with a label but no
    concepturi. The service drops those rather than emitting
    fragile half-records the editor would fail to apply."""
    broken_hit: dict[str, object] = {
        "id": "Q999999",
        "label": "Broken entity",
        "description": "Missing concepturi on purpose",
        # no concepturi
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"search": [_DANTE_HIT, broken_hit], "success": 1},
        )

    hits = await search(
        "dante", lang="it", limit=10,
        transport=httpx.MockTransport(handler),
    )
    assert [h.qid for h in hits] == ["Q1067"]


@pytest.mark.asyncio
async def test_search_falls_back_to_title_when_label_missing() -> None:
    hit: dict[str, object] = {
        "id": "Q100",
        # no "label"
        "title": "Q100",
        "concepturi": "http://www.wikidata.org/entity/Q100",
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"search": [hit]})

    hits = await search(
        "x", lang="it", limit=10,
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1
    assert hits[0].label == "Q100"


@pytest.mark.asyncio
async def test_search_limit_clamped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"search": [_DANTE_HIT]})

    # limit=0 → clamped to 1, limit=999 → clamped to 25. Upstream
    # receives the clamped value in the query string.
    captured: dict[str, object] = {}

    def handler_capture(request: httpx.Request) -> httpx.Response:
        captured.setdefault("urls", []).append(str(request.url))  # type: ignore[attr-defined]
        return httpx.Response(200, json={"search": [_DANTE_HIT]})

    await search("x", limit=0, transport=httpx.MockTransport(handler_capture))
    await search("x", limit=999, transport=httpx.MockTransport(handler_capture))
    urls = captured["urls"]  # type: ignore[index]
    assert any("limit=1" in u for u in urls)  # type: ignore[arg-type]
    assert any("limit=25" in u for u in urls)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search(
        "x", transport=httpx.MockTransport(handler),
    )
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hits = await search(
        "x", transport=httpx.MockTransport(handler),
    )
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    hits = await search(
        "x", transport=httpx.MockTransport(handler),
    )
    assert hits == []


@pytest.mark.asyncio
async def test_search_empty_search_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"search": [], "success": 1})

    hits = await search(
        "nonexistentthing12345", transport=httpx.MockTransport(handler),
    )
    assert hits == []
