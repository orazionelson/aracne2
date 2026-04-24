"""Maintenance mode for public websites.

Covers the two-primitive design:

1. ``Website.maintenance_on_unpublish`` flag gates the automatic
   behaviour. Defaults are per rendering mode (STATIC=False,
   DYNAMIC=True, HYBRID=True).
2. When active and the linked collection is not published+public, any
   ``/api/v1/sites/{slug}/*`` request returns **503** with a HTML
   banner and a ``Retry-After`` header.

Plus the defaults applied on creation, the per-website override, and
the fallback logic for contact email.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.user import User
from app.models.website import RenderingMode, Website
from app.tests.conftest import DESIGNER_PASSWORD, DESIGNER_USERNAME


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _mk_collection(
    db: AsyncSession,
    *,
    slug: str,
    title: str = "Collection",
    status: CollectionStatus = CollectionStatus.published,
    is_public: bool = True,
) -> Collection:
    col = Collection(
        slug=slug,
        title=title,
        description=f"Description of {title}",
        status=status,
        is_public=is_public,
    )
    db.add(col)
    await db.flush()
    return col


@pytest_asyncio.fixture
async def dynamic_website(
    db_session: AsyncSession,
    seeded_designer: User,
) -> tuple[Website, Collection]:
    col = await _mk_collection(db_session, slug="published-col")
    website = Website(
        slug="dyn-site",
        title="Dynamic Site",
        collection_id=col.id,
        rendering_mode=RenderingMode.DYNAMIC,
        is_published=True,
        maintenance_on_unpublish=True,
        created_by=seeded_designer.id,
    )
    db_session.add(website)
    await db_session.flush()
    await db_session.refresh(website, attribute_names=["pages", "indices"])
    return website, col


@pytest_asyncio.fixture
async def static_website(
    db_session: AsyncSession,
    seeded_designer: User,
) -> tuple[Website, Collection]:
    col = await _mk_collection(db_session, slug="published-col-static")
    website = Website(
        slug="static-site",
        title="Static Site",
        collection_id=col.id,
        rendering_mode=RenderingMode.STATIC,
        is_published=True,
        maintenance_on_unpublish=False,  # STATIC default
        created_by=seeded_designer.id,
    )
    db_session.add(website)
    await db_session.flush()
    await db_session.refresh(website, attribute_names=["pages", "indices"])
    return website, col


# ── Defaults applied at creation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_dynamic_defaults_maintenance_true(
    client: AsyncClient, seeded_designer: User,
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/websites",
        headers=_auth(token),
        json={
            "slug": "dyn-default",
            "title": "Dyn Default",
            "rendering_mode": "DYNAMIC",
        },
    )
    assert res.status_code == 201
    assert res.json()["data"]["maintenance_on_unpublish"] is True


@pytest.mark.asyncio
async def test_create_hybrid_defaults_maintenance_true(
    client: AsyncClient, seeded_designer: User,
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/websites",
        headers=_auth(token),
        json={
            "slug": "hyb-default",
            "title": "Hyb Default",
            "rendering_mode": "HYBRID",
        },
    )
    assert res.status_code == 201
    assert res.json()["data"]["maintenance_on_unpublish"] is True


@pytest.mark.asyncio
async def test_create_static_defaults_maintenance_false(
    client: AsyncClient, seeded_designer: User,
) -> None:
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/websites",
        headers=_auth(token),
        json={
            "slug": "sta-default",
            "title": "Sta Default",
            "rendering_mode": "STATIC",
        },
    )
    assert res.status_code == 201
    assert res.json()["data"]["maintenance_on_unpublish"] is False


@pytest.mark.asyncio
async def test_create_accepts_explicit_override(
    client: AsyncClient, seeded_designer: User,
) -> None:
    """Caller can force the flag regardless of rendering mode."""
    token = await _login_as(client, DESIGNER_USERNAME, DESIGNER_PASSWORD)
    res = await client.post(
        "/api/v1/websites",
        headers=_auth(token),
        json={
            "slug": "sta-forced",
            "title": "Static with forced maintenance",
            "rendering_mode": "STATIC",
            "maintenance_on_unpublish": True,
        },
    )
    assert res.status_code == 201
    assert res.json()["data"]["maintenance_on_unpublish"] is True


# ── Behaviour at render time — collection published = normal ─────────────────


@pytest.mark.asyncio
async def test_dynamic_site_serves_normally_when_collection_published(
    client_with_existdb: AsyncClient,
    dynamic_website: tuple[Website, Collection],
) -> None:
    website, _col = dynamic_website
    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    # Not 503 — collection is published, maintenance must not fire.
    assert res.status_code != 503


# ── Behaviour when collection is unpublished ────────────────────────────────


@pytest.mark.asyncio
async def test_dynamic_site_returns_503_when_collection_unpublished(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    dynamic_website: tuple[Website, Collection],
) -> None:
    website, col = dynamic_website
    col.status = CollectionStatus.assigned  # i.e. unpublished
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    assert res.status_code == 503
    assert res.headers["retry-after"] == "3600"
    assert res.headers.get("x-robots-tag", "").startswith("noindex")
    assert "text/html" in res.headers["content-type"]
    # Title of the site appears in the banner body.
    assert website.title in res.text


@pytest.mark.asyncio
async def test_dynamic_site_returns_503_when_collection_private(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    dynamic_website: tuple[Website, Collection],
) -> None:
    website, col = dynamic_website
    col.is_public = False  # published but private
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/browse")
    assert res.status_code == 503


@pytest.mark.asyncio
async def test_static_site_ignores_unpublish_when_flag_false(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    static_website: tuple[Website, Collection],
) -> None:
    """STATIC site with maintenance_on_unpublish=False must keep serving
    (or 404 because no files on disk — anything except 503)."""
    website, col = static_website
    col.status = CollectionStatus.assigned
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    assert res.status_code != 503


@pytest.mark.asyncio
async def test_static_site_with_maintenance_flag_on_returns_503(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    static_website: tuple[Website, Collection],
) -> None:
    """STATIC site that the Designer explicitly opted in to — same
    503 behaviour as DYNAMIC when the collection is unpublished."""
    website, col = static_website
    website.maintenance_on_unpublish = True
    col.status = CollectionStatus.assigned
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    assert res.status_code == 503


# ── Banner content: message + contact email fallback ───────────────────────


@pytest.mark.asyncio
async def test_banner_uses_custom_message_when_set(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    dynamic_website: tuple[Website, Collection],
) -> None:
    website, col = dynamic_website
    website.maintenance_message = "Back online Monday. Thank you for patience."
    col.status = CollectionStatus.assigned
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    assert res.status_code == 503
    assert "Back online Monday" in res.text


@pytest.mark.asyncio
async def test_banner_shows_website_contact_email_when_set(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    dynamic_website: tuple[Website, Collection],
) -> None:
    website, col = dynamic_website
    website.contact_email = "curator@example.org"
    col.status = CollectionStatus.assigned
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    assert res.status_code == 503
    assert "curator@example.org" in res.text


@pytest.mark.asyncio
async def test_banner_falls_back_to_admin_email_when_contact_empty(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    dynamic_website: tuple[Website, Collection],
) -> None:
    website, col = dynamic_website
    # contact_email left as default (None)
    col.status = CollectionStatus.assigned
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    assert res.status_code == 503
    from app.config import settings as app_settings
    assert app_settings.admin_email in res.text


@pytest.mark.asyncio
async def test_maintenance_css_is_enclosed_in_style_tag(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    dynamic_website: tuple[Website, Collection],
) -> None:
    """Regression: the ``.maint-wrap`` stylesheet must ship inside the
    page's ``<style>`` block, not leak into the body as plain text.
    """
    website, col = dynamic_website
    col.status = CollectionStatus.assigned
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    assert res.status_code == 503
    head, _, tail = res.text.partition("</style>")
    # The maintenance selector must live in <head> before </style> closes,
    # never in the body that follows it.
    assert ".maint-wrap" in head
    assert ".maint-wrap" not in tail


@pytest.mark.asyncio
async def test_website_without_collection_never_enters_maintenance(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_designer: User,
) -> None:
    website = Website(
        slug="no-col",
        title="Dangling site",
        collection_id=None,  # no link
        rendering_mode=RenderingMode.DYNAMIC,
        is_published=True,
        maintenance_on_unpublish=True,
        created_by=seeded_designer.id,
    )
    db_session.add(website)
    await db_session.flush()

    res = await client_with_existdb.get(f"/api/v1/sites/{website.slug}/")
    # Anything except 503 — no collection to gate on.
    assert res.status_code != 503
