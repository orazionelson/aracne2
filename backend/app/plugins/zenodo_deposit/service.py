"""Zenodo REST client used by the deposit plugin.

Docs: https://developers.zenodo.org/

The client is intentionally small — it only implements the five calls the
deposit flow needs (create draft, upload file to bucket, attach metadata,
publish, read back).  Anything more elaborate belongs in its own module.

Transport is httpx.AsyncClient; for testability the caller can inject a
custom transport (e.g. ``httpx.MockTransport`` in tests) via the
``transport`` constructor argument.
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
    """Minimal view of a Zenodo deposition draft response."""

    id: int
    bucket_url: str
    record_url: str


@dataclass(frozen=True)
class DepositResult:
    """Outcome of a full deposit flow — draft or published."""

    id: int
    doi: str | None
    record_url: str
    status: str  # "draft" | "published"


class ZenodoClient:
    """Async client for the Zenodo Deposition API."""

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
            "User-Agent": "Aracne2-ZenodoDeposit/1.0",
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
        retry_5xx: bool = True,
    ) -> httpx.Response:
        """Issue one request with exponential backoff on 5xx + transport errors."""
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with self._client() as client:
                    resp = await client.request(method, url, json=json, content=content)
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
        # Exhausted retries — surface the last known error.
        if isinstance(last_exc, ZenodoError):
            raise last_exc
        raise ZenodoError(f"Zenodo request failed: {last_exc}") from last_exc

    # ── High-level operations ─────────────────────────────────────────────────

    async def create_draft(self) -> DepositDraft:
        """Create an empty deposition and return its id + bucket_url + record_url."""
        resp = await self._request(
            "POST", f"{self._base}/api/deposit/depositions", json={}
        )
        payload = resp.json()
        try:
            draft = DepositDraft(
                id=int(payload["id"]),
                bucket_url=str(payload["links"]["bucket"]),
                record_url=str(payload["links"]["html"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ZenodoError(f"Malformed create-draft response: {exc}") from exc
        logger.info("zenodo_draft_created", deposit_id=draft.id)
        return draft

    async def upload_file(
        self, bucket_url: str, filename: str, content: bytes
    ) -> None:
        """Upload a single file to a deposition's bucket using the new files API."""
        url = f"{bucket_url.rstrip('/')}/{filename}"
        await self._request("PUT", url, content=content)
        logger.info("zenodo_file_uploaded", filename=filename, size=len(content))

    async def update_metadata(self, deposit_id: int, payload: dict[str, Any]) -> None:
        """Attach metadata to a deposition draft."""
        url = f"{self._base}/api/deposit/depositions/{deposit_id}"
        await self._request("PUT", url, json=payload)
        logger.info("zenodo_metadata_attached", deposit_id=deposit_id)

    async def publish(self, deposit_id: int) -> DepositResult:
        """Publish a deposition.  Returns the finalised record with DOI."""
        url = f"{self._base}/api/deposit/depositions/{deposit_id}/actions/publish"
        resp = await self._request("POST", url)
        data = resp.json()
        return DepositResult(
            id=int(data.get("id", deposit_id)),
            doi=str(data.get("doi")) if data.get("doi") else None,
            record_url=str(data.get("links", {}).get("html", "")),
            status="published",
        )


def _describe_error(resp: httpx.Response) -> str:
    """Produce a compact error description from a Zenodo non-success response."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 — best-effort diagnosis only
        return f"Zenodo {resp.status_code}: {resp.text[:200]}"
    msg = body.get("message") or body.get("status") or resp.text[:200]
    errors = body.get("errors")
    if errors:
        return f"Zenodo {resp.status_code}: {msg} ({errors})"
    return f"Zenodo {resp.status_code}: {msg}"
