"""Tests for the websites management endpoints (/websites/*).

Metadata CRUD tests use the standard ``client`` fixture (Postgres-only).
Endpoints that call eXist-db patch ``app.services.websites.existdb_client``.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.models.website import Website
from app.tests.conftest import (
    DESIGNER_PASSWORD,
    DESIGNER_USERNAME,
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
async def seeded_website(db_session: AsyncSession, seeded_designer: User) -> Website:
    website = Website(
        slug="test-website",
        title="Test Website",
        created_by=seeded_designer.id,
    )
    db_session.add(website)
    await db_session.flush()
    return website


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_websites_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    """Designer can list websites."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get("/api/v1/websites", headers=_auth(token))
    assert res.status_code == 200
    slugs = [w["slug"] for w in res.json()["data"]]
    assert "test-website" in slugs


@pytest.mark.asyncio
async def test_list_websites_as_editor_returns_403(
    client: AsyncClient, seeded_user: User
) -> None:
    """Editor (no Designer role) cannot access the website list."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get("/api/v1/websites", headers=_auth(token))
    assert res.status_code == 403


# ── Create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_website_as_designer(
    client: AsyncClient, seeded_designer: User
) -> None:
    """Designer can create a new website."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/websites",
        headers=_auth(token),
        json={"slug": "new-site", "title": "New Site"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["slug"] == "new-site"


# ── Get ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_website_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        f"/api/v1/websites/{seeded_website.slug}", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["data"]["slug"] == seeded_website.slug


@pytest.mark.asyncio
async def test_get_nonexistent_website_returns_404(
    client: AsyncClient, seeded_designer: User
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get("/api/v1/websites/does-not-exist", headers=_auth(token))
    assert res.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_website_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.put(
        f"/api/v1/websites/{seeded_website.slug}",
        headers=_auth(token),
        json={"slug": seeded_website.slug, "title": "Updated Title"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "Updated Title"


# ── Delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_website_as_designer(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.delete(
        f"/api/v1/websites/{seeded_website.slug}", headers=_auth(token)
    )
    assert res.status_code == 204


# ── Pages ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_website_page(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    """Designer can add a page to a website."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        f"/api/v1/websites/{seeded_website.slug}/pages",
        headers=_auth(token),
        json={"slug": "about", "title": "About"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["slug"] == "about"


@pytest.mark.asyncio
async def test_update_website_page(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    """Designer can update a page title."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    await client.post(
        f"/api/v1/websites/{seeded_website.slug}/pages",
        headers=_auth(token),
        json={"slug": "contact", "title": "Contact"},
    )
    res = await client.put(
        f"/api/v1/websites/{seeded_website.slug}/pages/contact",
        headers=_auth(token),
        json={"title": "Contact Us"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "Contact Us"


@pytest.mark.asyncio
async def test_delete_website_page(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    """Designer can delete a page."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    await client.post(
        f"/api/v1/websites/{seeded_website.slug}/pages",
        headers=_auth(token),
        json={"slug": "deleteme", "title": "Delete Me"},
    )
    res = await client.delete(
        f"/api/v1/websites/{seeded_website.slug}/pages/deleteme",
        headers=_auth(token),
    )
    assert res.status_code == 204


# ── Indices ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_website_indices(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        f"/api/v1/websites/{seeded_website.slug}/indices", headers=_auth(token)
    )
    assert res.status_code == 200
    assert isinstance(res.json()["data"], list)


@pytest.mark.asyncio
async def test_create_website_index(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        f"/api/v1/websites/{seeded_website.slug}/indices",
        headers=_auth(token),
        json={"label": "persons", "title": "Persons", "tag": "persName"},
    )
    assert res.status_code == 201
    assert res.json()["data"]["label"] == "persons"


@pytest.mark.asyncio
async def test_update_website_index(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    create_res = await client.post(
        f"/api/v1/websites/{seeded_website.slug}/indices",
        headers=_auth(token),
        json={"label": "places", "title": "Places", "tag": "placeName"},
    )
    assert create_res.status_code == 201
    idx_id = create_res.json()["data"]["id"]
    res = await client.put(
        f"/api/v1/websites/{seeded_website.slug}/indices/{idx_id}",
        headers=_auth(token),
        json={"label": "places-updated", "tag": "placeName"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["label"] == "places-updated"


@pytest.mark.asyncio
async def test_delete_website_index(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    create_res = await client.post(
        f"/api/v1/websites/{seeded_website.slug}/indices",
        headers=_auth(token),
        json={"label": "orgs", "title": "Orgs", "tag": "orgName"},
    )
    assert create_res.status_code == 201
    idx_id = create_res.json()["data"]["id"]
    res = await client.delete(
        f"/api/v1/websites/{seeded_website.slug}/indices/{idx_id}",
        headers=_auth(token),
    )
    assert res.status_code == 204


# ── eXist-db-dependent endpoints ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_tags_calls_existdb(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_designer: User,
    seeded_website: Website,
) -> None:
    """Refresh tags endpoint triggers eXist-db XQuery and returns 200."""
    # The service requires website.collection_id to be set.
    col = Collection(
        slug="tags-col",
        title="Tags Collection",
        status=CollectionStatus.published,
        is_public=True,
    )
    db_session.add(col)
    await db_session.flush()
    seeded_website.collection_id = col.id
    await db_session.flush()

    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    with patch("app.services.websites.existdb_client") as mock_db:
        mock_db.xquery = AsyncMock(return_value=b"[]")
        mock_db.col_path = lambda slug: f"/db/aracne2/collections/{slug}"
        res = await client.post(
            f"/api/v1/websites/{seeded_website.slug}/tags/refresh",
            headers=_auth(token),
        )
    assert res.status_code == 200


# ── New fields: website_url and show_in_public_home ───────────────────────────


@pytest.mark.asyncio
async def test_create_website_with_url_and_public_home_flag(
    client: AsyncClient, seeded_designer: User
) -> None:
    """Designer can set website_url and show_in_public_home when creating a website."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/websites",
        headers=_auth(token),
        json={
            "slug": "site-with-url",
            "title": "Site With URL",
            "website_url": "https://example.com",
            "show_in_public_home": True,
        },
    )
    assert res.status_code == 201
    data = res.json()["data"]
    assert data["website_url"] == "https://example.com"
    assert data["show_in_public_home"] is True


@pytest.mark.asyncio
async def test_update_website_url_and_public_home_flag(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    """Designer can update website_url and show_in_public_home on an existing website."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.put(
        f"/api/v1/websites/{seeded_website.slug}",
        headers=_auth(token),
        json={
            "slug": seeded_website.slug,
            "title": seeded_website.title,
            "website_url": "https://updated.example.com",
            "show_in_public_home": True,
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["website_url"] == "https://updated.example.com"
    assert data["show_in_public_home"] is True


@pytest.mark.asyncio
async def test_website_url_defaults_to_none(
    client: AsyncClient, seeded_designer: User, seeded_website: Website
) -> None:
    """A website created without website_url has website_url=None and show_in_public_home=False."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.get(
        f"/api/v1/websites/{seeded_website.slug}", headers=_auth(token)
    )
    assert res.status_code == 200
    assert res.json()["data"]["website_url"] is None
    assert res.json()["data"]["show_in_public_home"] is False
