"""Tests for the sitemap / robots.txt endpoints.

All exercised against the in-memory test app via the ``client_with_existdb``
fixture (which also overrides ``get_existdb`` with an AsyncMock).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.search_engine import SearchEngine
from app.models.system_setting import SystemSetting
from app.models.website import BuildStatus, Website, WebsitePage

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_settings(db_session: AsyncSession) -> None:
    """Seed the settings the SEO router consults.

    public_base_url pins the origin emitted in every loc, so the
    assertions do not depend on what the test client advertises.
    """
    db_session.add(
        SystemSetting(
            key="public_base_url",
            value="https://edition.example.org",
            type="string",
        )
    )
    db_session.add(
        SystemSetting(
            key="sitemap_include_search_engines", value="false", type="bool"
        )
    )
    db_session.add(
        SystemSetting(key="public_home_enabled", value="false", type="bool")
    )
    await db_session.flush()


@pytest_asyncio.fixture
async def public_collection(
    db_session: AsyncSession, seeded_settings: None
) -> Collection:
    col = Collection(
        slug="divina-commedia",
        title="Divina Commedia",
        status=CollectionStatus.published,
        is_public=True,
    )
    db_session.add(col)
    await db_session.flush()
    return col


@pytest_asyncio.fixture
async def draft_collection(
    db_session: AsyncSession, seeded_settings: None
) -> Collection:
    """A collection that the sitemap MUST NOT advertise."""
    col = Collection(
        slug="wip",
        title="Work in progress",
        status=CollectionStatus.draft,
        is_public=False,
    )
    db_session.add(col)
    await db_session.flush()
    return col


@pytest_asyncio.fixture
async def published_website(
    db_session: AsyncSession, seeded_settings: None
) -> Website:
    site = Website(
        slug="my-site",
        title="My Site",
        is_published=True,
        build_status=BuildStatus.done,
    )
    db_session.add(site)
    await db_session.flush()
    db_session.add_all([
        WebsitePage(
            website_id=site.id,
            slug="about",
            title="About",
            is_hidden=False,
            sort_order=1,
        ),
        WebsitePage(
            website_id=site.id,
            slug="secret",
            title="Secret",
            is_hidden=True,
            sort_order=2,
        ),
    ])
    await db_session.flush()
    return site


@pytest_asyncio.fixture
async def built_search_engine(
    db_session: AsyncSession, seeded_settings: None
) -> SearchEngine:
    se = SearchEngine(
        slug="global-search",
        title="Global Search",
        build_status=BuildStatus.done,
        advanced_search_enabled=True,
    )
    db_session.add(se)
    await db_session.flush()
    return se


# ── robots.txt ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_robots_txt_lists_sitemap_and_disallows_admin(
    client_with_existdb: AsyncClient, seeded_settings: None
) -> None:
    res = await client_with_existdb.get("/api/v1/robots.txt")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    body = res.text
    assert "User-agent: *" in body
    assert "Sitemap: https://edition.example.org/sitemap.xml" in body
    assert "Disallow: /admin/" in body


@pytest.mark.asyncio
async def test_robots_txt_falls_back_to_request_origin_when_unset(
    client_with_existdb: AsyncClient, db_session: AsyncSession
) -> None:
    """With no public_base_url seeded the robots.txt must still emit a
    sitemap line — using the request's origin as fallback."""
    # Seed minimal (no public_base_url row at all).
    db_session.add(
        SystemSetting(key="sitemap_include_search_engines", value="false", type="bool")
    )
    db_session.add(SystemSetting(key="public_home_enabled", value="false", type="bool"))
    await db_session.flush()
    res = await client_with_existdb.get("/api/v1/robots.txt")
    assert res.status_code == 200
    # Fallback origin has scheme+host, whatever the test client chose.
    assert "Sitemap:" in res.text
    assert "/sitemap.xml" in res.text


# ── sitemap index ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sitemap_index_lists_core_and_websites_by_default(
    client_with_existdb: AsyncClient, seeded_settings: None
) -> None:
    res = await client_with_existdb.get("/api/v1/sitemap.xml")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:sitemap/sm:loc", _NS)]
    assert "https://edition.example.org/sitemap-core.xml" in locs
    assert "https://edition.example.org/sitemap-websites.xml" in locs
    assert "https://edition.example.org/sitemap-search-engines.xml" not in locs


@pytest.mark.asyncio
async def test_sitemap_index_adds_search_engines_when_opt_in(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_settings: None,
) -> None:
    row = await db_session.get(SystemSetting, "sitemap_include_search_engines")
    assert row is not None
    row.value = "true"
    await db_session.flush()

    res = await client_with_existdb.get("/api/v1/sitemap.xml")
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:sitemap/sm:loc", _NS)]
    assert "https://edition.example.org/sitemap-search-engines.xml" in locs


# ── sitemap-core.xml ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sitemap_core_includes_public_published_collections(
    client_with_existdb: AsyncClient,
    public_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    # Two documents in the published snapshot for this collection (Phase A2:
    # the sitemap reads from the snapshot, not the working tree).
    mock_existdb.list_published = AsyncMock(
        return_value=["inferno.xml", "purgatorio.xml"]
    )
    res = await client_with_existdb.get("/api/v1/sitemap-core.xml")
    assert res.status_code == 200
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert "https://edition.example.org/browse/divina-commedia" in locs
    assert "https://edition.example.org/browse/divina-commedia/inferno.xml" in locs
    assert "https://edition.example.org/browse/divina-commedia/purgatorio.xml" in locs


@pytest.mark.asyncio
async def test_sitemap_core_excludes_draft_and_private_collections(
    client_with_existdb: AsyncClient,
    draft_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    res = await client_with_existdb.get("/api/v1/sitemap-core.xml")
    assert res.status_code == 200
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert not any("wip" in loc for loc in locs), locs


@pytest.mark.asyncio
async def test_sitemap_core_includes_home_when_enabled(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_settings: None,
    mock_existdb: AsyncMock,
) -> None:
    row = await db_session.get(SystemSetting, "public_home_enabled")
    assert row is not None
    row.value = "true"
    await db_session.flush()
    res = await client_with_existdb.get("/api/v1/sitemap-core.xml")
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert "https://edition.example.org/" in locs


@pytest.mark.asyncio
async def test_sitemap_core_survives_existdb_failure(
    client_with_existdb: AsyncClient,
    public_collection: Collection,
    mock_existdb: AsyncMock,
) -> None:
    """A hiccup from eXist-db must not 500 the sitemap — the collection
    URL is still emitted, only its document entries are skipped."""
    mock_existdb.list_published = AsyncMock(side_effect=RuntimeError("boom"))
    res = await client_with_existdb.get("/api/v1/sitemap-core.xml")
    assert res.status_code == 200
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert "https://edition.example.org/browse/divina-commedia" in locs


# ── sitemap-websites.xml ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sitemap_websites_includes_pages_but_skips_hidden(
    client_with_existdb: AsyncClient, published_website: Website
) -> None:
    res = await client_with_existdb.get("/api/v1/sitemap-websites.xml")
    assert res.status_code == 200
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert "https://edition.example.org/sites/my-site/" in locs
    assert "https://edition.example.org/sites/my-site/browse" in locs
    assert "https://edition.example.org/sites/my-site/pages/about" in locs
    assert not any("pages/secret" in loc for loc in locs), locs


@pytest.mark.asyncio
async def test_sitemap_websites_excludes_unpublished(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_settings: None,
) -> None:
    db_session.add(
        Website(
            slug="draft-site",
            title="Draft",
            is_published=False,
            build_status=BuildStatus.idle,
        )
    )
    await db_session.flush()
    res = await client_with_existdb.get("/api/v1/sitemap-websites.xml")
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert locs == []


# ── sitemap-search-engines.xml ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sitemap_search_engines_empty_when_opt_in_off(
    client_with_existdb: AsyncClient,
    built_search_engine: SearchEngine,
) -> None:
    """Even with built engines, the setting gates the output — the sitemap
    returns an empty urlset (not 404) so the discovered URL stays stable."""
    res = await client_with_existdb.get("/api/v1/sitemap-search-engines.xml")
    assert res.status_code == 200
    root = ET.fromstring(res.text)
    assert root.findall(".//sm:url", _NS) == []


@pytest.mark.asyncio
async def test_sitemap_search_engines_lists_built_engines_when_opt_in(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    built_search_engine: SearchEngine,
) -> None:
    row = await db_session.get(SystemSetting, "sitemap_include_search_engines")
    assert row is not None
    row.value = "true"
    await db_session.flush()

    res = await client_with_existdb.get("/api/v1/sitemap-search-engines.xml")
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert "https://edition.example.org/search-pages/global-search/" in locs
    # advanced_search_enabled=True on the fixture → the advanced page is there too.
    assert "https://edition.example.org/search-pages/global-search/advanced/" in locs


@pytest.mark.asyncio
async def test_sitemap_search_engines_skips_unbuilt(
    client_with_existdb: AsyncClient,
    db_session: AsyncSession,
    seeded_settings: None,
) -> None:
    row = await db_session.get(SystemSetting, "sitemap_include_search_engines")
    assert row is not None
    row.value = "true"
    # Add an idle engine — must be excluded.
    db_session.add(
        SearchEngine(slug="not-built", title="NB", build_status=BuildStatus.idle)
    )
    await db_session.flush()
    res = await client_with_existdb.get("/api/v1/sitemap-search-engines.xml")
    root = ET.fromstring(res.text)
    locs = [el.text for el in root.findall(".//sm:url/sm:loc", _NS)]
    assert locs == []
