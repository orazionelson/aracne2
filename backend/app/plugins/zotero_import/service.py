"""Zotero Web API v3 client (read-only).

Docs: https://www.zotero.org/support/dev/web_api/v3/basics

Only exercises ``GET {library_url}/items``: the plugin is import-only,
it never writes to Zotero. Pagination follows the ``Link: rel="next"``
header convention documented by Zotero (RFC 5988).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_TIMEOUT = 30.0
# Zotero's max page size is 100 (v3 API). Going smaller just
# multiplies round-trips, so we pin to the maximum.
_PAGE_SIZE = 100
# Zotero's docs suggest honouring ``Backoff`` / ``Retry-After`` headers on
# 429. For an MVP we keep things simple — a 429 surfaces as an error the
# caller can show to the admin; the typical import is under the
# ~500-request-per-5-minute soft cap anyway.


class ZoteroError(RuntimeError):
    """Raised on unrecoverable Zotero API failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ZoteroItem:
    """One item as returned by Zotero — the subset we actually use."""

    key: str
    data: dict[str, Any]  # raw ``data`` object from the API response


# ``Link: <...>; rel="next", <...>; rel="last"``  — capture only the next url.
_LINK_NEXT_RE = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


class ZoteroClient:
    """Async, paginating, read-only client for one Zotero library."""

    def __init__(
        self,
        *,
        api_key: str,
        library_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ZoteroError("Zotero API key is empty")
        if not library_url:
            raise ZoteroError("Zotero library URL is empty")
        self._api_key = api_key
        self._library_url = library_url.rstrip("/")
        # v3 accepts either ``Zotero-API-Key`` header or ``Bearer``; the
        # header form is what Zotero's own docs use in examples.
        self._headers = {
            "Zotero-API-Version": "3",
            "Zotero-API-Key": api_key,
            "User-Agent": "Aracne2-ZoteroImport/1.0",
            "Accept": "application/json",
        }
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": _TIMEOUT, "headers": self._headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def fetch_all_items(self) -> list[ZoteroItem]:
        """Return every item in the library, following ``Link: rel="next"``
        until exhausted. Skips Zotero's "notes", "attachments", and
        "linked files" item types — none of which map to a TEI biblStruct.
        """
        url: str | None = (
            f"{self._library_url}/items?format=json&limit={_PAGE_SIZE}"
            "&itemType=-note%20||%20-attachment"
        )
        collected: list[ZoteroItem] = []
        page_count = 0

        async with self._client() as client:
            while url:
                page_count += 1
                try:
                    resp = await client.get(url)
                except httpx.RequestError as exc:
                    raise ZoteroError(f"Request failed: {exc}") from exc
                if not resp.is_success:
                    raise ZoteroError(
                        _describe_error(resp),
                        status_code=resp.status_code,
                    )
                try:
                    body = resp.json()
                except ValueError as exc:
                    raise ZoteroError(
                        f"Zotero returned non-JSON: {exc}"
                    ) from exc

                if not isinstance(body, list):
                    raise ZoteroError("Zotero response root was not a list")

                for raw in body:
                    if not isinstance(raw, dict):
                        continue
                    key = raw.get("key")
                    data = raw.get("data")
                    if not isinstance(key, str) or not isinstance(data, dict):
                        continue
                    # Extra safety: skip types with no bibliographic shape.
                    item_type = data.get("itemType")
                    if item_type in {"note", "attachment", "annotation"}:
                        continue
                    collected.append(ZoteroItem(key=key, data=data))

                # Zotero paginates via ``Link`` header (RFC 5988). When
                # the server omits rel="next" we're done.
                link = resp.headers.get("Link") or resp.headers.get("link")
                url = _extract_next(link) if link else None

        logger.info(
            "zotero_fetch_ok", pages=page_count, items=len(collected)
        )
        return collected


def _extract_next(link_header: str) -> str | None:
    match = _LINK_NEXT_RE.search(link_header)
    return match.group(1) if match else None


def _describe_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return f"Zotero {resp.status_code}: {resp.text[:200]}"
    if isinstance(body, dict):
        msg = body.get("message") or body.get("error") or resp.text[:200]
    else:
        msg = resp.text[:200]
    return f"Zotero {resp.status_code}: {msg}"
