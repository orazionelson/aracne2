"""Internet Archive "Save Page Now 2" (SPN2) REST client.

Docs: https://archive.org/help/wayback_api.php (Save Page Now API section).

Two endpoints exercised:

- ``POST https://web.archive.org/save/`` — submit a URL for capture;
  returns ``{job_id, url}`` when accepted.
- ``GET  https://web.archive.org/save/status/{job_id}`` — poll the job;
  returns ``{status: "pending" | "success" | "error", …}``. On success
  the response carries ``timestamp`` which, combined with ``original_url``,
  builds the canonical Wayback URL ``/web/{timestamp}/{original_url}``.

Auth is S3-style ``Authorization: LOW {access}:{secret}`` — quirky but
that is literally what the docs call for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_BASE_URL = "https://web.archive.org"
_SUBMIT_URL = f"{_BASE_URL}/save/"
_STATUS_URL = f"{_BASE_URL}/save/status"
_TIMEOUT = 30.0


class IAError(RuntimeError):
    """Raised on non-recoverable SPN2 errors or transport failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SubmitResult:
    """Outcome of a submit: the opaque SPN2 job id + the URL that was submitted."""

    job_id: str
    url: str


@dataclass(frozen=True)
class StatusResult:
    """Outcome of a status poll.

    ``status`` normalises SPN2's lifecycle values onto our three-value
    axis. ``wayback_url`` is populated only when ``status == 'success'``.
    ``error`` is populated only when ``status == 'failed'``.
    """

    status: str  # "pending" | "success" | "failed"
    timestamp: str | None
    original_url: str | None
    wayback_url: str | None
    error: str | None


def _wayback_url(timestamp: str, original_url: str) -> str:
    return f"{_BASE_URL}/web/{timestamp}/{original_url}"


class InternetArchiveClient:
    """Small async client for Save Page Now 2."""

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not access_key or not secret_key:
            raise IAError("Internet Archive API keys are not set")
        self._headers = {
            "Authorization": f"LOW {access_key}:{secret_key}",
            "Accept": "application/json",
            "User-Agent": "Aracne2-InternetArchive/1.0",
        }
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": _TIMEOUT, "headers": self._headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def submit(self, url: str) -> SubmitResult:
        """Submit *url* for capture. Returns the SPN2 job id."""
        data = {
            "url": url,
            # capture_all tells IA to include error pages in the record so
            # a flaky 502 from our side does not produce a partial capture.
            "capture_all": "1",
        }
        async with self._client() as client:
            try:
                resp = await client.post(_SUBMIT_URL, data=data)
            except httpx.RequestError as exc:
                raise IAError(f"Submit failed: {exc}") from exc

        if not resp.is_success:
            raise IAError(
                _describe_error(resp),
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise IAError(f"Submit response was not JSON: {exc}") from exc
        job_id = payload.get("job_id")
        original_url = payload.get("url", url)
        if not isinstance(job_id, str) or not job_id:
            raise IAError(f"Submit response lacked job_id: {payload}")
        logger.info("ia_submit_ok", job_id=job_id, url=url)
        return SubmitResult(job_id=job_id, url=str(original_url))

    async def status(self, job_id: str) -> StatusResult:
        """Poll one SPN2 job. Maps SPN2's lifecycle to our three-value axis."""
        url = f"{_STATUS_URL}/{job_id}"
        async with self._client() as client:
            try:
                resp = await client.get(url)
            except httpx.RequestError as exc:
                raise IAError(f"Status poll failed: {exc}") from exc

        if not resp.is_success:
            raise IAError(
                _describe_error(resp),
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise IAError(f"Status response was not JSON: {exc}") from exc

        raw_status = str(payload.get("status") or "").lower()
        if raw_status == "success":
            timestamp = payload.get("timestamp")
            original = payload.get("original_url")
            if not (isinstance(timestamp, str) and isinstance(original, str)):
                # Shape regression on the upstream — surface as failure.
                return StatusResult(
                    status="failed",
                    timestamp=None,
                    original_url=None,
                    wayback_url=None,
                    error="Malformed success response",
                )
            return StatusResult(
                status="success",
                timestamp=timestamp,
                original_url=original,
                wayback_url=_wayback_url(timestamp, original),
                error=None,
            )
        if raw_status == "pending":
            return StatusResult(
                status="pending",
                timestamp=None,
                original_url=None,
                wayback_url=None,
                error=None,
            )
        # Everything else (error, blocked, …) collapses to failed. SPN2's
        # ``message`` field carries a human-readable explanation when set.
        message = payload.get("message") or payload.get("status_ext") or raw_status or "unknown error"
        return StatusResult(
            status="failed",
            timestamp=None,
            original_url=payload.get("original_url") if isinstance(payload.get("original_url"), str) else None,
            wayback_url=None,
            error=str(message),
        )


def _describe_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return f"IA {resp.status_code}: {resp.text[:200]}"
    msg = body.get("message") or body.get("status_ext") or resp.text[:200]
    return f"IA {resp.status_code}: {msg}"
