"""Minimal HTTP client wrapper used by every command.

Wraps a synchronous ``httpx.Client`` so the typer commands can stay
straightforward (no asyncio loop juggling). Concurrency for bulk
imports/exports is handled at a higher level (``concurrent.futures``)
so the client itself can stay request-scoped and stateless.

The only thing the wrapper adds over raw ``httpx`` is:
- Authorization header injection (PAT bearer)
- ``DataResponse`` envelope unwrapping (the backend wraps every JSON
  body in ``{"data": ...}`` per ``API_FORMAT.md``)
- Tidy error rendering (the backend's ``error.code`` / ``error.message``
  surface, not raw HTTPX exceptions)

Tests inject a custom ``httpx.MockTransport`` via the ``transport``
constructor argument so no real backend is needed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class ApiError(RuntimeError):
    """Wraps a backend-side error response.

    The :attr:`code` is the ``error.code`` SCREAMING_SNAKE_CASE
    constant from the backend; tests assert on it instead of the
    user-facing message which is locale-dependent.
    """

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code} ({status_code}): {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details or {})


class ApiClient:
    """Thin sync httpx wrapper.

    Construct once per command (the typer command opens a context
    manager); use :meth:`get` / :meth:`post` / :meth:`put` / :meth:`delete`
    which return the *unwrapped* ``data`` field from the backend
    envelope.
    """

    def __init__(
        self,
        host: str,
        token: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=host.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _api_path(self, path: str) -> str:
        if path.startswith("/api/"):
            return path
        if path.startswith("/"):
            return f"/api/v1{path}"
        return f"/api/v1/{path}"

    def _raise_for(self, response: httpx.Response) -> None:
        """Translate a non-2xx response into :class:`ApiError`.

        The backend's error envelope is ``{"error": {"code": "...",
        "message": "...", "details": {}}}``; if the body is not JSON
        (rare — gateway 502, malformed deployment) we synthesise an
        ``UNKNOWN`` code from the status text.
        """
        if response.is_success:
            return
        try:
            payload = response.json()
        except (ValueError, httpx.DecodingError):
            payload = {}
        err = payload.get("error", {}) if isinstance(payload, dict) else {}
        raise ApiError(
            status_code=response.status_code,
            code=str(err.get("code") or "UNKNOWN_ERROR"),
            message=str(err.get("message") or response.text or response.reason_phrase),
            details=err.get("details") or {},
        )

    def _unwrap(self, response: httpx.Response) -> Any:
        if response.status_code == 204 or not response.content:
            return None
        try:
            payload = response.json()
        except (ValueError, httpx.DecodingError):
            return response.text
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # ── Verbs ────────────────────────────────────────────────────────────────

    def get(self, path: str, *, params: Mapping[str, str] | None = None) -> Any:
        r = self._client.get(self._api_path(path), params=params)
        self._raise_for(r)
        return self._unwrap(r)

    def get_raw(
        self, path: str, *, params: Mapping[str, str] | None = None
    ) -> httpx.Response:
        """Like :meth:`get`, but returns the raw response so the caller
        can read non-JSON bodies (e.g. raw XML from a document endpoint)
        without going through the envelope unwrapper.
        """
        r = self._client.get(self._api_path(path), params=params)
        self._raise_for(r)
        return r

    def post(self, path: str, *, json: Any = None) -> Any:
        r = self._client.post(self._api_path(path), json=json)
        self._raise_for(r)
        return self._unwrap(r)

    def post_multipart(
        self, path: str, files: Mapping[str, tuple[str, bytes, str]]
    ) -> Any:
        r = self._client.post(self._api_path(path), files=files)
        self._raise_for(r)
        return self._unwrap(r)

    def put(self, path: str, *, content: bytes, content_type: str) -> Any:
        r = self._client.put(
            self._api_path(path),
            content=content,
            headers={"Content-Type": content_type},
        )
        self._raise_for(r)
        return self._unwrap(r)

    def delete(self, path: str) -> Any:
        r = self._client.delete(self._api_path(path))
        self._raise_for(r)
        return self._unwrap(r)
