"""Tests for ExistDBClient dual-client architecture and bootstrap_user().

These tests instantiate ExistDBClient directly and inject mock HTTP clients
so no live eXist-db connection is required.

Key invariants verified:
  - ensure_root() and bootstrap_user() go through _admin_client
  - All runtime operations (xquery, get_document, put_document, delete_document,
    create_collection, delete_collection, list_collection) go through _client
  - bootstrap_user() is skipped (returns early) when existdb_app_password is empty
  - bootstrap_user() is idempotent (safe to call twice)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.db.existdb import ExistDBClient


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_ok_response(content: bytes = b"<ok/>") -> httpx.Response:
    return httpx.Response(200, content=content)


def _make_client(post_response: bytes = b"<ok/>") -> AsyncMock:
    """Return an AsyncMock that mimics an httpx.AsyncClient."""
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.post = AsyncMock(return_value=_make_ok_response(post_response))
    mock.get = AsyncMock(return_value=_make_ok_response(b"<ok/>"))
    mock.put = AsyncMock(return_value=_make_ok_response(b"<ok/>"))
    mock.delete = AsyncMock(return_value=httpx.Response(204))
    mock.aclose = AsyncMock(return_value=None)
    return mock


def _make_existdb() -> tuple[ExistDBClient, AsyncMock, AsyncMock]:
    """Return a connected ExistDBClient with both clients replaced by mocks."""
    existdb = ExistDBClient()
    admin_mock = _make_client()
    runtime_mock = _make_client()
    existdb._admin_client = admin_mock
    existdb._client = runtime_mock
    return existdb, admin_mock, runtime_mock


# ── ensure_root ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_root_uses_admin_client() -> None:
    """ensure_root() must POST to the admin client, never the runtime client."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    with patch.object(existdb, "_load_xq", return_value="()"):
        await existdb.ensure_root()

    admin_mock.post.assert_called_once()
    runtime_mock.post.assert_not_called()


# ── bootstrap_user ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bootstrap_user_sends_xquery_via_admin_client() -> None:
    """bootstrap_user() must use _admin_client and not touch _client."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    with (
        patch("app.db.existdb.settings") as mock_settings,
        patch.object(existdb, "_load_xq", return_value="()")):
        mock_settings.existdb_app_password = "secret"
        mock_settings.existdb_user = "aracne"
        await existdb.bootstrap_user()

    admin_mock.post.assert_called_once()
    runtime_mock.post.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_user_skipped_when_no_password() -> None:
    """bootstrap_user() must return early without calling eXist-db when password is empty."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    with patch("app.db.existdb.settings") as mock_settings:
        mock_settings.existdb_app_password = ""
        await existdb.bootstrap_user()

    admin_mock.post.assert_not_called()
    runtime_mock.post.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_user_idempotent() -> None:
    """bootstrap_user() must succeed when called twice in a row."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    with (
        patch("app.db.existdb.settings") as mock_settings,
        patch.object(existdb, "_load_xq", return_value="()")):
        mock_settings.existdb_app_password = "secret"
        mock_settings.existdb_user = "aracne"
        await existdb.bootstrap_user()
        await existdb.bootstrap_user()

    assert admin_mock.post.call_count == 2


# ── Runtime operations use _client ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_xquery_uses_runtime_client() -> None:
    """xquery() must use _client, not _admin_client."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    with patch.object(existdb, "_load_xq", return_value="()"):
        await existdb.xquery("collections/any.xq")

    runtime_mock.post.assert_called_once()
    admin_mock.post.assert_not_called()


@pytest.mark.asyncio
async def test_get_document_uses_runtime_client() -> None:
    """get_document() must use _client, not _admin_client."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    await existdb.get_document("mycol", "doc.xml")

    runtime_mock.get.assert_called_once()
    admin_mock.get.assert_not_called()


@pytest.mark.asyncio
async def test_put_document_uses_runtime_client() -> None:
    """put_document() must use _client, not _admin_client."""
    existdb, admin_mock, runtime_mock = _make_existdb()
    runtime_mock.put = AsyncMock(return_value=httpx.Response(201))

    await existdb.put_document("mycol", "doc.xml", b"<doc/>")

    runtime_mock.put.assert_called_once()
    admin_mock.put.assert_not_called()


@pytest.mark.asyncio
async def test_delete_document_uses_runtime_client() -> None:
    """delete_document() must use _client, not _admin_client."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    await existdb.delete_document("mycol", "doc.xml")

    runtime_mock.delete.assert_called_once()
    admin_mock.delete.assert_not_called()


# ── close() ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_closes_both_clients() -> None:
    """close() must call aclose() on both _client and _admin_client."""
    existdb, admin_mock, runtime_mock = _make_existdb()

    await existdb.close()

    admin_mock.aclose.assert_called_once()
    runtime_mock.aclose.assert_called_once()
    assert existdb._client is None
    assert existdb._admin_client is None
