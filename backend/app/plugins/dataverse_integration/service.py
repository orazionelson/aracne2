"""Dataverse REST client used by the deposit plugin.

Docs: https://guides.dataverse.org/en/latest/api/native-api.html

Flow used by the deposit orchestration:
  POST /api/dataverses/{alias}/datasets               # create dataset (mints DOI)
  POST /api/datasets/:persistentId/add?persistentId=  # add one file
  POST /api/datasets/:persistentId/actions/:publish   # publish (release the DOI)

Auth: ``X-Dataverse-key: <token>``.

Important quirk: Dataverse mints the DOI **immediately on dataset
creation** (in DRAFT state) — the same DOI string is returned by
``create_dataset`` and by ``publish``. The DOI is *preallocated* on
the draft and only *resolves* via the public DOI registry after
publish; before that, link the dataset's landing page directly via
``{base}/dataset.xhtml?persistentId=doi:<DOI>``.

The client is small — it implements only what the deposit flow
needs. Tests inject an ``httpx.AsyncBaseTransport`` (e.g.
``httpx.MockTransport``) via the ``transport`` constructor argument.
"""

from __future__ import annotations

import asyncio
import json as _json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_TIMEOUT = 30.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds: 2, 4


class DataverseError(RuntimeError):
    """Raised on unrecoverable Dataverse API failures.

    The ``status_code`` attribute carries the HTTP code (when set)
    so callers can distinguish auth (401) from server outage (5xx)
    without parsing the message.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DatasetDraft:
    """A freshly-created Dataverse dataset draft.

    ``persistent_id`` is the DOI string (e.g. ``doi:10.5072/FK2/AB12CD``)
    that Dataverse minted at creation time. ``database_id`` is the
    Dataverse-internal numeric id, useful for some endpoint variants.
    """

    persistent_id: str
    database_id: int | None
    landing_url: str


@dataclass(frozen=True)
class DepositResult:
    """Outcome of the full deposit flow — draft or published."""

    persistent_id: str
    doi: str  # bare DOI without ``doi:`` prefix, suitable for display
    landing_url: str
    status: str  # "draft" | "published"


class DataverseClient:
    """Async client for the Dataverse REST API.

    ``base_url`` is the Dataverse instance root
    (``https://demo.dataverse.org`` or
    ``https://dataverse.<institution>.it``); the adapter appends
    ``/api/...`` itself.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_token:
            raise DataverseError("Dataverse API token is empty")
        self._base = base_url.rstrip("/")
        self._headers = {
            "X-Dataverse-key": api_token,
            "User-Agent": "Aracne2-Dataverse/1.0",
        }
        self._transport = transport

    # ── Low-level HTTP ────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "timeout": _TIMEOUT, "headers": self._headers,
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        retry_5xx: bool = True,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with self._client() as client:
                    resp = await client.request(
                        method, url,
                        json=json, files=files, data=data, params=params,
                    )
                if 500 <= resp.status_code < 600 and retry_5xx:
                    last_exc = DataverseError(
                        f"Dataverse {resp.status_code} at {url}",
                        status_code=resp.status_code,
                    )
                else:
                    if not resp.is_success:
                        raise DataverseError(
                            _describe_error(resp),
                            status_code=resp.status_code,
                        )
                    return resp
            except httpx.RequestError as exc:
                last_exc = exc
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE ** attempt)
        if isinstance(last_exc, DataverseError):
            raise last_exc
        raise DataverseError(
            f"Dataverse request failed: {last_exc}",
        ) from last_exc

    # ── High-level operations ─────────────────────────────────────────────

    async def create_dataset(
        self, alias: str, payload: dict[str, Any],
    ) -> DatasetDraft:
        """Create a new dataset under ``alias`` with the given metadata.

        ``payload`` is the full Dataverse dataset shape:
        ``{"datasetVersion": {"metadataBlocks": {"citation": {...}}}}``.
        Mapping → payload is the responsibility of ``mapping.py``.

        Returns a ``DatasetDraft`` carrying the persistent ID (DOI)
        Dataverse minted on creation — even though the dataset is in
        DRAFT state and the DOI is not yet resolvable via doi.org.
        """
        url = f"{self._base}/api/dataverses/{alias}/datasets"
        resp = await self._request("POST", url, json=payload)
        body = resp.json()
        data = body.get("data") or {}
        pid = data.get("persistentId")
        if not isinstance(pid, str) or not pid:
            raise DataverseError(
                f"Malformed create-dataset response (no persistentId): {body}",
            )
        db_id = data.get("id") if isinstance(data.get("id"), int) else None
        landing_url = (
            f"{self._base}/dataset.xhtml?persistentId={pid}"
        )
        logger.info(
            "dataverse_dataset_created",
            persistent_id=pid, database_id=db_id, alias=alias,
        )
        return DatasetDraft(
            persistent_id=pid,
            database_id=db_id,
            landing_url=landing_url,
        )

    async def upload_file(
        self,
        persistent_id: str,
        filename: str,
        content: bytes,
        *,
        directory_label: str | None = None,
        description: str | None = None,
    ) -> None:
        """Upload one file to an existing dataset draft.

        ``directory_label`` becomes the folder shown in the Dataverse
        Files tab (``"docs/"``, ``"css/"``, …) — Dataverse honours this
        for nested website trees. ``description`` is optional per-file
        text shown in the file metadata panel.
        """
        url = f"{self._base}/api/datasets/:persistentId/add"
        json_data: dict[str, Any] = {}
        if directory_label:
            json_data["directoryLabel"] = directory_label
        if description:
            json_data["description"] = description
        files = {
            "file": (filename, content, "application/octet-stream"),
        }
        # Dataverse's multipart contract: ``file`` part for the binary,
        # ``jsonData`` part for the per-file metadata as a JSON string.
        data = {"jsonData": _json.dumps(json_data)} if json_data else {}
        await self._request(
            "POST", url,
            files=files,
            data=data,
            params={"persistentId": persistent_id},
        )
        logger.info(
            "dataverse_file_uploaded",
            persistent_id=persistent_id,
            filename=filename,
            size=len(content),
        )

    async def publish(
        self, persistent_id: str, *, publish_type: str = "major",
    ) -> DepositResult:
        """Publish a draft dataset.

        ``publish_type`` is one of ``major`` (default — publishes a 1.0
        / 2.0 / … version), ``minor`` (1.1 / 1.2 / …) or
        ``updatecurrent`` (in-place update of the current version,
        super-user only).
        """
        url = f"{self._base}/api/datasets/:persistentId/actions/:publish"
        resp = await self._request(
            "POST", url,
            params={"persistentId": persistent_id, "type": publish_type},
        )
        body = resp.json()
        data = body.get("data") or {}
        pid = data.get("persistentUrl") or data.get("persistentId") or persistent_id
        # ``persistentUrl`` is e.g. "https://doi.org/10.5072/FK2/AB12CD" —
        # extract the bare DOI for our DepositResult.
        bare_doi = _extract_bare_doi(pid) or _extract_bare_doi(persistent_id) or ""
        return DepositResult(
            persistent_id=persistent_id,
            doi=bare_doi,
            landing_url=f"{self._base}/dataset.xhtml?persistentId={persistent_id}",
            status="published",
        )

    async def list_dataverses(self) -> list[dict[str, Any]]:
        """Return the list of root-level Dataverses on this instance.

        Used by the admin config page to populate a dropdown of valid
        ``default_alias`` values; falls back to a free-text input when
        the call fails (no permissions / unreachable instance).
        """
        url = f"{self._base}/api/dataverses/:root/contents"
        resp = await self._request("GET", url, retry_5xx=False)
        body = resp.json()
        items = body.get("data") or []
        if not isinstance(items, list):
            return []
        return [it for it in items if isinstance(it, dict) and it.get("type") == "dataverse"]


def _extract_bare_doi(s: str) -> str | None:
    """Best-effort: pull the bare DOI from a doi: prefixed string or
    a https://doi.org/... URL. Returns None when no DOI shape matches."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    for prefix in ("doi:", "https://doi.org/", "http://doi.org/"):
        if s.lower().startswith(prefix):
            return s[len(prefix):]
    # Already a bare DOI? Rough check: starts with "10." and contains "/".
    if s.startswith("10.") and "/" in s:
        return s
    return None


def _describe_error(resp: httpx.Response) -> str:
    """Compact error description from a non-success response."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 — best-effort diagnosis only
        return f"Dataverse {resp.status_code}: {resp.text[:200]}"
    msg = body.get("message") or body.get("status") or resp.text[:200]
    return f"Dataverse {resp.status_code}: {msg}"
