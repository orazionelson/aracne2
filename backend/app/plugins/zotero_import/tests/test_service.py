"""ZoteroClient tests backed by httpx.MockTransport — no network."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.zotero_import.service import ZoteroClient, ZoteroError


def _client(handler: httpx.MockTransport) -> ZoteroClient:
    return ZoteroClient(
        api_key="ZK-test",
        library_url="https://api.zotero.org/groups/12345",
        transport=handler,
    )


@pytest.mark.asyncio
async def test_fetch_all_items_follows_link_next() -> None:
    """A two-page library is enumerated via the Link: rel="next" header."""
    pages = [
        (
            [
                {"key": "AAA", "data": {"itemType": "book", "title": "A"}},
                {"key": "BBB", "data": {"itemType": "book", "title": "B"}},
            ],
            # first page points to a second page
            '<https://api.zotero.org/groups/12345/items?start=2>; rel="next"',
        ),
        (
            [
                {"key": "CCC", "data": {"itemType": "journalArticle", "title": "C"}},
            ],
            # last page: no next link
            "",
        ),
    ]
    state = {"page": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body, link = pages[state["page"]]
        state["page"] += 1
        headers = {"Link": link} if link else {}
        assert request.headers["Zotero-API-Key"] == "ZK-test"
        assert request.headers["Zotero-API-Version"] == "3"
        return httpx.Response(200, json=body, headers=headers)

    result = await _client(httpx.MockTransport(handler)).fetch_all_items()
    assert [i.key for i in result] == ["AAA", "BBB", "CCC"]
    assert state["page"] == 2  # two pages consumed


@pytest.mark.asyncio
async def test_fetch_skips_notes_and_attachments() -> None:
    """Zotero items of type ``note`` / ``attachment`` / ``annotation`` are
    filtered out even when the server accidentally returns them."""
    def handler(_: httpx.Request) -> httpx.Response:
        body = [
            {"key": "A", "data": {"itemType": "note", "note": "x"}},
            {"key": "B", "data": {"itemType": "attachment", "filename": "x.pdf"}},
            {"key": "C", "data": {"itemType": "annotation"}},
            {"key": "D", "data": {"itemType": "book", "title": "real"}},
        ]
        return httpx.Response(200, json=body)

    result = await _client(httpx.MockTransport(handler)).fetch_all_items()
    assert [i.key for i in result] == ["D"]


@pytest.mark.asyncio
async def test_missing_key_or_data_entry_is_dropped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        body = [
            {"key": "A"},  # no data
            {"data": {"itemType": "book", "title": "x"}},  # no key
            {"key": "B", "data": {"itemType": "book", "title": "ok"}},
        ]
        return httpx.Response(200, json=body)

    result = await _client(httpx.MockTransport(handler)).fetch_all_items()
    assert [i.key for i in result] == ["B"]


@pytest.mark.asyncio
async def test_403_raises_zotero_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"message": "Not authorised to access this library"}
        )

    with pytest.raises(ZoteroError) as exc:
        await _client(httpx.MockTransport(handler)).fetch_all_items()
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_429_raises_zotero_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limit"})

    with pytest.raises(ZoteroError) as exc:
        await _client(httpx.MockTransport(handler)).fetch_all_items()
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_constructor_rejects_empty_credentials() -> None:
    with pytest.raises(ZoteroError):
        ZoteroClient(api_key="", library_url="https://api.zotero.org/groups/1")
    with pytest.raises(ZoteroError):
        ZoteroClient(api_key="x", library_url="")
