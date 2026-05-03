"""SEO — sitemap + robots.txt generation.

Pure(ish) helpers that build the XML for each sub-sitemap. The router
is a thin wrapper that reads the public base URL from system_settings
(or falls back to the incoming request origin) and serialises the
lists returned by this module.

Shape decisions:

- A single ``/sitemap.xml`` acts as a sitemap **index** per the
  sitemaps.org protocol, pointing to sub-sitemaps that are small and
  easy to regenerate.
- ``/sitemap-core.xml`` — the public collections and their documents,
  plus the public home page when it is enabled.
- ``/sitemap-websites.xml`` — each published Website's landing page
  (``/sites/{slug}/``), browse index, and visible pages.
- ``/sitemap-search-engines.xml`` — opt-in per
  ``sitemap_include_search_engines``. Lists the built search pages.

URLs emitted for crawlers follow the SPA paths (``/browse/…``,
``/sites/…``, ``/search-pages/…``) rather than the API paths, matching
the LOD URIs already produced by ``public_view`` and expecting that
nginx fronts both the SPA and the backend under the same origin.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient
from app.models.collection import Collection, CollectionStatus
from app.models.search_engine import SearchEngine
from app.models.website import BuildStatus, Website, WebsitePage

# sitemaps.org namespace — required on every sitemap element.
_SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


# Registering the default namespace once ensures ET.tostring emits
# ``<urlset xmlns="…">`` without ``ns0:`` prefixes.
ET.register_namespace("", _SM_NS)


@dataclass(frozen=True)
class SitemapEntry:
    """One row in a urlset: URL + optional lastmod."""

    loc: str
    lastmod: datetime | None = None


# ── helpers ────────────────────────────────────────────────────────────────


def _iso_date(d: datetime) -> str:
    """Sitemaps accept W3C Datetime; ``YYYY-MM-DD`` is the safest subset."""
    return d.date().isoformat()


def _urlset(entries: list[SitemapEntry]) -> str:
    """Serialise a list of entries as a ``<urlset>`` sitemap document."""
    root = ET.Element(f"{{{_SM_NS}}}urlset")
    for entry in entries:
        url_el = ET.SubElement(root, f"{{{_SM_NS}}}url")
        ET.SubElement(url_el, f"{{{_SM_NS}}}loc").text = entry.loc
        if entry.lastmod is not None:
            ET.SubElement(url_el, f"{{{_SM_NS}}}lastmod").text = _iso_date(entry.lastmod)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def _sitemapindex(entries: list[SitemapEntry]) -> str:
    """Serialise a sitemap *index*: one ``<sitemap>`` per sub-sitemap."""
    root = ET.Element(f"{{{_SM_NS}}}sitemapindex")
    for entry in entries:
        sm = ET.SubElement(root, f"{{{_SM_NS}}}sitemap")
        ET.SubElement(sm, f"{{{_SM_NS}}}loc").text = entry.loc
        if entry.lastmod is not None:
            ET.SubElement(sm, f"{{{_SM_NS}}}lastmod").text = _iso_date(entry.lastmod)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def _abs(base: str, path: str) -> str:
    """Join a base origin and a root-relative path without doubling slashes."""
    return f"{base.rstrip('/')}{path}"


# ── entry builders ─────────────────────────────────────────────────────────


async def build_core_entries(
    db: AsyncSession, existdb: ExistDBClient, base_url: str, *, include_home: bool
) -> list[SitemapEntry]:
    """Public collections + their documents (+ optional public home)."""
    entries: list[SitemapEntry] = []

    if include_home:
        entries.append(SitemapEntry(loc=_abs(base_url, "/")))

    rows = await db.scalars(
        select(Collection)
        .where(
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
        .order_by(Collection.title)
    )
    collections = list(rows)

    for col in collections:
        entries.append(
            SitemapEntry(
                loc=_abs(base_url, f"/browse/{col.slug}"),
                lastmod=col.updated_at,
            )
        )
        # Documents live in eXist-db; each collection may error
        # independently (missing eXist-db container, auth issue) — we
        # log-and-continue so one bad collection never breaks the
        # sitemap for the rest of the corpus.
        try:
            filenames = await existdb.list_published(col.slug)
        except Exception:  # noqa: BLE001 — sitemap must not 500 on eXist-db hiccups
            filenames = []
        for filename in filenames:
            entries.append(
                SitemapEntry(
                    loc=_abs(base_url, f"/browse/{col.slug}/{quote(filename, safe='')}"),
                    # Re-use the collection's updated_at as a conservative
                    # proxy; eXist-db does not expose per-document mtime
                    # in a way that we can cheaply fan out from here.
                    lastmod=col.updated_at,
                )
            )

    return entries


async def build_website_entries(
    db: AsyncSession, base_url: str
) -> list[SitemapEntry]:
    """Published websites: landing + browse + visible pages."""
    entries: list[SitemapEntry] = []

    sites = list(
        await db.scalars(
            select(Website)
            .where(Website.is_published.is_(True))
            .order_by(Website.title)
        )
    )

    for site in sites:
        entries.append(
            SitemapEntry(
                loc=_abs(base_url, f"/sites/{site.slug}/"),
                lastmod=site.updated_at,
            )
        )
        entries.append(
            SitemapEntry(
                loc=_abs(base_url, f"/sites/{site.slug}/browse"),
                lastmod=site.updated_at,
            )
        )
        pages = list(
            await db.scalars(
                select(WebsitePage)
                .where(
                    WebsitePage.website_id == site.id,
                    WebsitePage.is_hidden.is_(False),
                )
                .order_by(WebsitePage.sort_order)
            )
        )
        for page in pages:
            entries.append(
                SitemapEntry(
                    loc=_abs(base_url, f"/sites/{site.slug}/pages/{page.slug}"),
                    lastmod=page.updated_at,
                )
            )

    return entries


async def build_search_engine_entries(
    db: AsyncSession, base_url: str
) -> list[SitemapEntry]:
    """Built (``build_status == done``) search engines.

    SearchEngine has no ``is_published`` column; "built" is the honest
    analogue — the static search page only exists on disk after a
    successful build. We also emit the advanced search page when the
    feature is enabled.
    """
    entries: list[SitemapEntry] = []
    engines = list(
        await db.scalars(
            select(SearchEngine)
            .where(SearchEngine.build_status == BuildStatus.done)
            .order_by(SearchEngine.title)
        )
    )
    for se in engines:
        entries.append(
            SitemapEntry(
                loc=_abs(base_url, f"/search-pages/{se.slug}/"),
                lastmod=se.last_build_at,
            )
        )
        if se.advanced_search_enabled:
            entries.append(
                SitemapEntry(
                    loc=_abs(base_url, f"/search-pages/{se.slug}/advanced/"),
                    lastmod=se.last_build_at,
                )
            )
    return entries


# ── document builders ─────────────────────────────────────────────────────


def serialize_urlset(entries: list[SitemapEntry]) -> str:
    return _urlset(entries)


def serialize_index(entries: list[SitemapEntry]) -> str:
    return _sitemapindex(entries)


def build_robots_txt(base_url: str) -> str:
    """The platform's robots.txt — permissive for public, Disallow the admin
    area (behind auth, but crawlers should not waste budget on 401s), and
    advertise the sitemap index."""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /api/v1/admin\n"
        "\n"
        f"Sitemap: {_abs(base_url, '/sitemap.xml')}\n"
    )
