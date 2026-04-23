"""VIAF AutoSuggest service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.viaf.service import search


def _dante_hit() -> dict[str, object]:
    return {
        "displayForm": "Alighieri, Dante, 1265-1321",
        "nametype": "personal",
        "viafid": "27063124",
        "term": "alighieri",
        "recordID": "n78088775",
    }


def _unesco_hit() -> dict[str, object]:
    return {
        "displayForm": "UNESCO",
        "nametype": "corporate",
        "viafid": "130081493",
    }


@pytest.mark.asyncio
async def test_search_parses_personal_hit() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"result": [_dante_hit()]})

    hits = await search("dante", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.viaf_id == "27063124"
    assert hit.uri == "http://viaf.org/viaf/27063124"
    assert hit.display == "Alighieri, Dante, 1265-1321"
    assert hit.name_type == "personal"
    assert "viaf.org/viaf/AutoSuggest" in str(captured["url"])
    assert "query=dante" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_parses_corporate_hit() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": [_unesco_hit()]})

    hits = await search("unesco", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].name_type == "corporate"
    assert hits[0].viaf_id == "130081493"


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {
                "displayForm": f"Person {i}",
                "nametype": "personal",
                "viafid": str(10000 + i),
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"result": items})

    hits = await search("p", rows=5, transport=httpx.MockTransport(handler))
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_skips_rows_without_viaf_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": [
                    {"displayForm": "No id person", "nametype": "personal"},
                    _dante_hit(),
                ]
            },
        )

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].viaf_id == "27063124"


@pytest.mark.asyncio
async def test_search_skips_rows_without_display() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": [
                    {"viafid": "42", "nametype": "personal"},
                    _dante_hit(),
                ]
            },
        )

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].viaf_id == "27063124"


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_empty_result_list() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": []})

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_name_type_lowercased() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        item = _dante_hit()
        item["nametype"] = "Personal"  # some results come with capitalised type
        return httpx.Response(200, json={"result": [item]})

    hits = await search("dante", rows=10, transport=httpx.MockTransport(handler))
    assert hits[0].name_type == "personal"
