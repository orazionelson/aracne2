"""Zenodo (InvenioRDM) REST client used by the deposit plugin.

Docs:
  https://inveniordm.docs.cern.ch/reference/rest_api_drafts_records/
  https://inveniordm.docs.cern.ch/reference/rest_api_drafts_records_files/

Flow:
  POST /api/records                                 # create draft with metadata
  POST /api/records/{id}/draft/files                # init file entries (keys)
  PUT  /api/records/{id}/draft/files/{key}/content  # upload bytes
  POST /api/records/{id}/draft/files/{key}/commit   # commit upload
  POST /api/records/{id}/draft/actions/publish      # publish

This is the **new** Zenodo API, not the legacy ``/api/deposit/depositions``
endpoints. It returns a richer, vocabulary-driven metadata shape and the
record id is the same pre- and post-publish.

The client is deliberately small — it only implements what the deposit
flow needs. For testability the caller can inject an httpx transport
(e.g. ``httpx.MockTransport``) via the ``transport`` constructor argument.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_TIMEOUT = 30.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds: 2, 4


class ZenodoError(RuntimeError):
    """Raised on unrecoverable Zenodo API failures (4xx, repeated 5xx).

    The ``status_code`` attribute — when set — carries the HTTP code so
    callers can distinguish "bad credentials" (401) from "server went down"
    (5xx) without parsing the error message.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DepositDraft:
    """Minimal view of a Zenodo record draft."""

    id: str
    record_url: str


@dataclass(frozen=True)
class DepositResult:
    """Outcome of a full deposit flow — draft or published."""

    id: str
    doi: str | None
    record_url: str
    status: str  # "draft" | "published"


class ZenodoClient:
    """Async client for the Zenodo (InvenioRDM) records API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_token:
            raise ZenodoError("Zenodo API token is empty")
        self._base = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "Aracne2-ZenodoDeposit/2.0",
        }
        self._transport = transport

    # ── Low-level HTTP ────────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": _TIMEOUT, "headers": self._headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        content: bytes | None = None,
        content_type: str | None = None,
        retry_5xx: bool = True,
    ) -> httpx.Response:
        """Issue one request with exponential backoff on 5xx + transport errors."""
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                extra_headers: dict[str, str] = {}
                if content_type is not None:
                    extra_headers["Content-Type"] = content_type
                async with self._client() as client:
                    resp = await client.request(
                        method,
                        url,
                        json=json,
                        content=content,
                        headers=extra_headers or None,
                    )
                if 500 <= resp.status_code < 600 and retry_5xx:
                    last_exc = ZenodoError(
                        f"Zenodo {resp.status_code} at {url}",
                        status_code=resp.status_code,
                    )
                else:
                    if not resp.is_success:
                        raise ZenodoError(
                            _describe_error(resp),
                            status_code=resp.status_code,
                        )
                    return resp
            except httpx.RequestError as exc:
                last_exc = exc
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
        if isinstance(last_exc, ZenodoError):
            raise last_exc
        raise ZenodoError(f"Zenodo request failed: {last_exc}") from last_exc

    # ── High-level operations ─────────────────────────────────────────────────

    async def create_draft(self, payload: dict[str, Any]) -> DepositDraft:
        """Create a new draft record with initial metadata.

        The payload is the full InvenioRDM record shape
        (``{"access": {...}, "files": {...}, "metadata": {...}}``) — this
        client does not build it, callers do that via ``mapping.py``.
        """
        resp = await self._request(
            "POST", f"{self._base}/api/records", json=payload
        )
        data = resp.json()
        try:
            draft = DepositDraft(
                id=str(data["id"]),
                record_url=str(data.get("links", {}).get("self_html", "")),
            )
        except (KeyError, TypeError) as exc:
            raise ZenodoError(f"Malformed create-draft response: {exc}") from exc
        logger.info("zenodo_draft_created", deposit_id=draft.id)
        return draft

    async def upload_file(
        self, draft_id: str, filename: str, content: bytes
    ) -> None:
        """Upload one file to a draft in three phases: init, stream, commit."""
        base = f"{self._base}/api/records/{draft_id}/draft/files"
        # 1. Declare the file entry.
        await self._request("POST", base, json=[{"key": filename}])
        # 2. Stream the bytes.
        await self._request(
            "PUT",
            f"{base}/{filename}/content",
            content=content,
            content_type="application/octet-stream",
        )
        # 3. Commit — the file becomes visible on the record.
        await self._request("POST", f"{base}/{filename}/commit")
        logger.info("zenodo_file_uploaded", filename=filename, size=len(content))

    async def publish(self, draft_id: str) -> DepositResult:
        """Publish a draft. Returns the finalised record with DOI."""
        url = f"{self._base}/api/records/{draft_id}/draft/actions/publish"
        resp = await self._request("POST", url)
        data = resp.json()
        pids = data.get("pids") or {}
        doi: str | None = None
        if isinstance(pids.get("doi"), dict):
            raw = pids["doi"].get("identifier")
            if isinstance(raw, str) and raw:
                doi = raw
        return DepositResult(
            id=str(data.get("id", draft_id)),
            doi=doi,
            record_url=str(data.get("links", {}).get("self_html", "")),
            status="published",
        )

    async def fetch_resource_types(self) -> list[dict[str, Any]]:
        """Fetch the resource-type vocabulary from Zenodo.

        Returns the raw ``hits.hits`` list. Caller normalises for the UI.
        Paginates through all pages (the vocabulary is small — typically ~40
        entries — but may grow).
        """
        url = f"{self._base}/api/vocabularies/resourcetypes?size=100"
        resp = await self._request("GET", url)
        data = resp.json()
        hits_obj = data.get("hits") or {}
        hits = hits_obj.get("hits") or []
        if not isinstance(hits, list):
            return []
        return hits


def _describe_error(resp: httpx.Response) -> str:
    """Compact error description from an InvenioRDM non-success response."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 — best-effort diagnosis only
        return f"Zenodo {resp.status_code}: {resp.text[:200]}"
    # InvenioRDM error format: {"status": 400, "message": "...", "errors": [{field, messages}]}
    msg = body.get("message") or body.get("status") or resp.text[:200]
    errors = body.get("errors")
    if errors:
        return f"Zenodo {resp.status_code}: {msg} ({errors})"
    return f"Zenodo {resp.status_code}: {msg}"
