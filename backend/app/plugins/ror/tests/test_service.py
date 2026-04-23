"""ROR search service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.ror.service import search


def _harvard_item() -> dict[str, object]:
    return {
        "id": "https://ror.org/03vek6s52",
        "names": [
            {"value": "Harvard University", "types": ["ror_display", "label"]},
            {"value": "Harvard", "types": ["alias"]},
            {"value": "Université de Harvard", "types": ["label"]},
        ],
        "types": ["education"],
        "locations": [
            {"geonames_details": {"name": "Cambridge", "country_name": "United States"}}
        ],
    }


@pytest.mark.asyncio
async def test_search_parses_v2_hit() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json={"items": [_harvard_item()]})

    hits = await search("harvard", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.ror_id == "03vek6s52"
    assert hit.uri == "https://ror.org/03vek6s52"
    assert hit.name == "Harvard University"
    # Aliases keep the non-display names, in the order they appeared.
    assert "Harvard" in hit.aliases
    assert "Université de Harvard" in hit.aliases
    # Display name is not echoed in aliases.
    assert "Harvard University" not in hit.aliases
    assert hit.country == "United States"
    assert hit.types == ["education"]
    # Request used the v2 endpoint with the correct query param.
    assert "api.ror.org/v2/organizations" in str(captured["url"])
    assert "query=harvard" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    # ROR v2 always returns 20 items per page — the plugin slices locally.
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {
                "id": f"https://ror.org/zz{i:04d}",
                "names": [{"value": f"Inst {i}", "types": ["ror_display"]}],
                "types": [],
                "locations": [],
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"items": items})

    hits = await search("zz", rows=5, transport=httpx.MockTransport(handler))
    assert len(hits) == 5
    assert hits[0].name == "Inst 0"
    assert hits[-1].name == "Inst 4"


@pytest.mark.asyncio
async def test_search_rows_clamped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [_harvard_item()]})

    # rows=0 gets clamped to 1 (and the single item passes through).
    hits = await search("harvard", rows=0, transport=httpx.MockTransport(handler))
    assert len(hits) == 1

    # rows=999 gets clamped to 25, not the raw number.
    hits = await search("harvard", rows=999, transport=httpx.MockTransport(handler))
    assert len(hits) == 1  # only 1 real item in the response


@pytest.mark.asyncio
async def test_search_skips_items_without_display_name() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "https://ror.org/nodisplay",
                        # Only alias / acronym, no display
                        "names": [{"value": "acronym", "types": ["acronym"]}],
                    },
                    _harvard_item(),
                ]
            },
        )

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    # The acronym-only entry is kept via its fallback label if present;
    # here there is no "label" either, so it is skipped.
    assert len(hits) == 1
    assert hits[0].ror_id == "03vek6s52"


@pytest.mark.asyncio
async def test_search_falls_back_to_label_when_no_display() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "https://ror.org/labelonly",
                        "names": [
                            {"value": "Some Institute", "types": ["label"]},
                            {"value": "SI", "types": ["acronym"]},
                        ],
                    }
                ]
            },
        )

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].name == "Some Institute"
    assert "SI" in hits[0].aliases


@pytest.mark.asyncio
async def test_search_rejects_non_ror_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "https://example.com/not-ror",
                        "names": [{"value": "X", "types": ["ror_display"]}],
                    }
                ]
            },
        )

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "nope"})

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
        return httpx.Response(200, content=b"not-json", headers={"Content-Type": "application/json"})

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_handles_missing_locations() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        item = _harvard_item()
        del item["locations"]
        return httpx.Response(200, json={"items": [item]})

    hits = await search("x", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].country is None
