"""Shared pytest fixtures for the aracne-cli tests.

Two recurring needs:

- ``isolated_config``: redirect ``~/.aracne/config.toml`` to a tempdir
  via the ``ARACNE_CLI_CONFIG_HOME`` env var so the developer's real
  credentials are never touched.
- ``mock_transport``: build an ``httpx.MockTransport`` that mirrors
  the backend's ``DataResponse`` envelope without spinning up a real
  FastAPI app.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from aracne_cli.config import CONFIG_HOME_ENV


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run with ``ARACNE_CLI_CONFIG_HOME=<tmp>`` so writes never escape."""
    monkeypatch.setenv(CONFIG_HOME_ENV, str(tmp_path))
    return tmp_path


def _envelope(data: object, *, status_code: int = 200) -> httpx.Response:
    """Backend-style envelope helper used by route handlers in tests."""
    return httpx.Response(
        status_code=status_code,
        json={"data": data},
    )


def _error(*, status_code: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json={"error": {"code": code, "message": message, "details": {}}},
    )


@pytest.fixture
def envelope() -> Callable[..., httpx.Response]:
    """Expose the helper as a fixture so tests can build their own
    canned responses inline."""
    return _envelope


@pytest.fixture
def error_response() -> Callable[..., httpx.Response]:
    return _error


@pytest.fixture
def mock_backend() -> Iterator[Callable[..., httpx.MockTransport]]:
    """Factory that builds an ``httpx.MockTransport`` from a route map.

    Usage::

        def test_x(mock_backend):
            transport = mock_backend({
                ("GET", "/api/v1/auth/me"): envelope({"username": "alice"}),
            })
            client = ApiClient("http://h", "tok", transport=transport)

    Each call returns a fresh transport; the route map keys are
    ``(method, full_path)`` tuples — the path includes the
    ``/api/v1`` prefix because that's what the wrapper builds.
    """

    def _factory(routes: dict[tuple[str, str], httpx.Response | Callable[[httpx.Request], httpx.Response]]) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            key = (request.method, request.url.path)
            if key not in routes:
                # Helpful 404 so tests fail fast on typos.
                return _error(
                    status_code=404,
                    code="NOT_FOUND",
                    message=f"no mock route for {key}",
                )
            handler_or_response = routes[key]
            if callable(handler_or_response):
                return handler_or_response(request)
            return handler_or_response

        return httpx.MockTransport(handler)

    yield _factory
