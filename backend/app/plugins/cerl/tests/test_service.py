"""CERL Thesaurus service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.cerl.service import search


def _aldus_hit() -> dict[str, object]:
    return {
        "_id": "cnp01283953",
        "_source": {
            "type": "cnp",
            "headingName": "Aldus Manutius",
            "variantNames": ["Manuzio, Aldo", "Manutio, Aldo"],
            "biographicalData": "ca. 1449–1515",
            "nameOfPlace": "Venice",
        },
    }


def _venice_hit() -> dict[str, object]:
    return {
        "_id": "cnl00007170",
        "_source": {
            "type": "cnl",
            "headingName": "Venice",
            "variantNames": ["Venezia", "Venetia"],
        },
    }


def _imprint_hit() -> dict[str, object]:
    return {
        "_id": "cni00011234",
        "_source": {
            "type": "cni",
            "headingName": "Officina Aldina",
            "nameOfPlace": "Venice",
        },
    }


@pytest.mark.asyncio
async def test_search_parses_person_hit() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"hits": {"total": 1, "hits": [_aldus_hit()]}})

    hits = await search("aldus", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.cerl_id == "cnp01283953"
    assert hit.uri == "https://data.cerl.org/thesaurus/cnp01283953"
    assert hit.label == "Aldus Manutius"
    assert hit.kind == "person"
    assert "1449" in hit.detail
    assert "Venice" in hit.detail
    assert "Manuzio" in hit.detail  # variant surfaced
    assert "data.cerl.org" in str(captured["url"])
    assert "query=aldus" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_classifies_place() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": {"hits": [_venice_hit()]}})

    hits = await search("venice", transport=httpx.MockTransport(handler))
    assert hits[0].kind == "place"


@pytest.mark.asyncio
async def test_search_classifies_imprint() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": {"hits": [_imprint_hit()]}})

    hits = await search("aldina", transport=httpx.MockTransport(handler))
    assert hits[0].kind == "imprint"


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {
                "_id": f"cnp{i:08d}",
                "_source": {"type": "cnp", "headingName": f"Person {i}"},
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"hits": {"hits": items}})

    hits = await search("x", rows=5, transport=httpx.MockTransport(handler))
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_skips_items_without_heading() -> None:
    broken = [
        {"_id": "cnp99999999", "_source": {"type": "cnp"}},  # no headingName
        _aldus_hit(),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": {"hits": broken}})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].cerl_id == "cnp01283953"


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


@pytest.mark.asyncio
async def test_search_unknown_prefix_buckets_to_other() -> None:
    weird = {
        "_id": "xxx00000001",  # unknown prefix
        "_source": {"headingName": "Exotic entity"},
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hits": {"hits": [weird]}})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits[0].kind == "other"
