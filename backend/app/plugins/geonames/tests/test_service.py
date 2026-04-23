"""GeoNames plugin service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.geonames.service import build_uri, search


def _rome_item() -> dict[str, object]:
    return {
        "geonameId": 3169070,
        "name": "Rome",
        "adminName1": "Lazio",
        "countryName": "Italy",
        "fcl": "P",
    }


# ── URI builder ─────────────────────────────────────────────────────────────


def test_build_uri_web_format() -> None:
    assert build_uri("3169070", "web") == "https://www.geonames.org/3169070"


def test_build_uri_sws_format() -> None:
    assert build_uri("3169070", "sws") == "http://sws.geonames.org/3169070/"


# ── Search happy path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_parses_hit_and_composes_display() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"geonames": [_rome_item()]})

    hits = await search(
        "rome",
        username="alice",
        url_format="web",
        rows=5,
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.geoname_id == "3169070"
    assert hit.uri == "https://www.geonames.org/3169070"
    assert hit.display == "Rome, Lazio, Italy"
    assert hit.name == "Rome"
    assert hit.region == "Lazio"
    assert hit.country == "Italy"
    assert hit.feature_class == "P"
    # The username reached the upstream.
    assert "username=alice" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_respects_sws_format() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"geonames": [_rome_item()]})

    hits = await search(
        "rome", username="alice", url_format="sws",
        transport=httpx.MockTransport(handler),
    )
    assert hits[0].uri == "http://sws.geonames.org/3169070/"


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {
                "geonameId": 1000 + i,
                "name": f"Town {i}",
                "adminName1": "Region",
                "countryName": "Country",
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"geonames": items})

    hits = await search(
        "t", username="u", url_format="web", rows=5,
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_display_collapses_when_region_equals_name() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        item = _rome_item()
        item["adminName1"] = "Rome"  # same as name
        return httpx.Response(200, json={"geonames": [item]})

    hits = await search(
        "rome", username="u", url_format="web",
        transport=httpx.MockTransport(handler),
    )
    # "Rome, Italy" — duplicate "Rome" suppressed.
    assert hits[0].display == "Rome, Italy"


@pytest.mark.asyncio
async def test_search_skips_items_without_geoname_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {"name": "No id", "adminName1": "X", "countryName": "Y"},
            _rome_item(),
        ]
        return httpx.Response(200, json={"geonames": items})

    hits = await search(
        "x", username="u", url_format="web",
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1
    assert hits[0].geoname_id == "3169070"


@pytest.mark.asyncio
async def test_search_skips_items_without_name() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {"geonameId": 1},  # no name
            _rome_item(),
        ]
        return httpx.Response(200, json={"geonames": items})

    hits = await search(
        "x", username="u", url_format="web",
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1


# ── Fail-soft ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_returns_empty_on_quota_exhaustion() -> None:
    """GeoNames signals quota exhaustion via a ``status`` envelope on
    HTTP 200. The service treats this as a failed lookup."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": {
                    "message": "the hourly limit of 1000 credits has been exceeded",
                    "value": 19,
                }
            },
        )

    hits = await search(
        "rome", username="u", url_format="web",
        transport=httpx.MockTransport(handler),
    )
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search(
        "x", username="u", url_format="web",
        transport=httpx.MockTransport(handler),
    )
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hits = await search(
        "x", username="u", url_format="web",
        transport=httpx.MockTransport(handler),
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
        "x", username="u", url_format="web",
        transport=httpx.MockTransport(handler),
    )
    assert hits == []


@pytest.mark.asyncio
async def test_search_rows_clamped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"geonames": [_rome_item()]})

    # rows=0 clamps to 1, rows=999 clamps to 25.
    hits = await search(
        "rome", username="u", url_format="web", rows=0,
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1
    hits = await search(
        "rome", username="u", url_format="web", rows=999,
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1  # upstream returned 1
