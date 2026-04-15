"""Tests for the document media endpoints.

These endpoints are PostgreSQL-only (no eXist-db): _get_or_404 and
_assert_*_access only query Postgres.  Actual file I/O goes to a
temporary directory that is cleaned up after each test.
"""

import io
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_USER_PASSWORD,
    TEST_USER_USERNAME,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def assigned_collection(
    db_session: AsyncSession, seeded_user: User
) -> Collection:
    """A collection in 'assigned' state with seeded_user as the editor."""
    col = Collection(
        slug="media-test-col",
        title="Media Test Collection",
        status=CollectionStatus.assigned,
        editor_id=seeded_user.id,
    )
    db_session.add(col)
    await db_session.flush()
    return col


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_media_returns_empty_for_new_document(
    client: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    tmp_path: Path,
) -> None:
    """Listing media on a document with no uploads returns an empty list."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    with patch("app.services.media.settings") as mock_settings:
        mock_settings.documents_media_root = tmp_path
        res = await client.get(
            f"/api/v1/collections/{assigned_collection.slug}/documents/doc.xml/media",
            headers=_auth(token),
        )

    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_upload_media_as_editor_returns_201(
    client: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    tmp_path: Path,
) -> None:
    """An editor can upload an image to their assigned collection."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with patch("app.services.media.settings") as mock_settings:
        mock_settings.documents_media_root = tmp_path
        res = await client.post(
            f"/api/v1/collections/{assigned_collection.slug}/documents/doc.xml/media",
            headers=_auth(token),
            files={"file": ("test_image.png", io.BytesIO(png_bytes), "image/png")},
        )

    assert res.status_code == 201
    item = res.json()["data"]
    assert item["filename"].endswith(".png")
    assert item["content_type"] == "image/png"
    assert item["size"] > 0


@pytest.mark.asyncio
async def test_upload_media_with_invalid_extension_returns_422(
    client: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    tmp_path: Path,
) -> None:
    """Uploading a file with a disallowed extension returns a 422 error."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    with patch("app.services.media.settings") as mock_settings:
        mock_settings.documents_media_root = tmp_path
        res = await client.post(
            f"/api/v1/collections/{assigned_collection.slug}/documents/doc.xml/media",
            headers=_auth(token),
            files={"file": ("malicious.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )

    assert res.status_code == 422


@pytest.mark.asyncio
async def test_upload_media_unauthenticated_returns_401(
    client: AsyncClient,
    assigned_collection: Collection,
) -> None:
    """Unauthenticated upload attempt is rejected with 401."""
    res = await client.post(
        f"/api/v1/collections/{assigned_collection.slug}/documents/doc.xml/media",
        files={"file": ("test.png", io.BytesIO(b""), "image/png")},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_delete_media_nonexistent_returns_404(
    client: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    tmp_path: Path,
) -> None:
    """Deleting a media file that does not exist returns 404."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    with patch("app.services.media.settings") as mock_settings:
        mock_settings.documents_media_root = tmp_path
        res = await client.delete(
            f"/api/v1/collections/{assigned_collection.slug}/documents/doc.xml/media/ghost.png",
            headers=_auth(token),
        )

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_list_media_unauthenticated_returns_401(
    client: AsyncClient,
    assigned_collection: Collection,
) -> None:
    """Unauthenticated list request is rejected with 401."""
    res = await client.get(
        f"/api/v1/collections/{assigned_collection.slug}/documents/doc.xml/media"
    )
    assert res.status_code == 401


# ── Security: path-traversal via doc_filename ─────────────────────────────────


@pytest.mark.parametrize("bad_doc", [
    # Starts with a dot — rejected by _validate_filename regex
    ".hidden.xml",
    # No .xml extension — rejected by _validate_filename regex
    "no-extension",
    # Oversized name — rejected by _validate_filename length guard
    "a" * 300 + ".xml",
    # Contains a space — rejected by _validate_filename regex
    "my doc.xml",
])
@pytest.mark.asyncio
async def test_list_media_rejects_invalid_doc_filename(
    client: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
    bad_doc: str,
) -> None:
    """doc_filename values that violate the filename rules are rejected with 422.

    Note: classical ../path traversal strings (e.g. '../etc/passwd.xml') are
    normalised away by the HTTP layer before they reach the application, so
    FastAPI never routes them — the protection lives at the transport level.
    _validate_filename guards against filenames that DO reach the service but
    still contain potentially dangerous patterns.
    """
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        f"/api/v1/collections/{assigned_collection.slug}/documents/{bad_doc}/media",
        headers=_auth(token),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_upload_media_rejects_invalid_doc_filename(
    client: AsyncClient,
    seeded_user: User,
    assigned_collection: Collection,
) -> None:
    """Uploading to an invalid doc_filename (no .xml extension) is rejected with 422."""
    import io
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.post(
        f"/api/v1/collections/{assigned_collection.slug}/documents/.hidden.xml/media",
        headers=_auth(token),
        files={"file": ("img.png", io.BytesIO(b"PNG"), "image/png")},
    )
    assert res.status_code == 422
