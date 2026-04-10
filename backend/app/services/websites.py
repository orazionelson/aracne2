"""Website service — CRUD operations, static builder, and dynamic rendering.

STATIC mode generates a self-contained folder of HTML/CSS files at
``settings.websites_root / slug /``.  DYNAMIC and HYBRID modes render pages
at request time from eXist-db data.  All three modes share the same data model
(Website, WebsitePage) and the same HTML generation helpers.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import html as _html
import json
import re
import uuid
from urllib.parse import quote as _url_quote
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.services.xslt import apply_xslt
from app.db.existdb import existdb_client
from app.db.postgres import AsyncSessionLocal
from app.models.collection import Collection, CollectionStatus
from app.models.collection_permission import CollectionPermission
from app.models.role import Role, RoleName, UserRole
from app.models.user import User
from app.models.website import BuildStatus, RenderingMode, Website, WebsiteIndex, WebsitePage
from app.schemas.websites import (
    MetaSuggestionsResponse,
    WebsiteCreate,
    WebsiteIndexCreate,
    WebsiteIndexUpdate,
    WebsitePageCreate,
    WebsitePageUpdate,
    WebsiteUpdate,
)

logger = structlog.get_logger()


# ── In-process caches (DYNAMIC / HYBRID rendering) ───────────────────────────

# Default TTL for rendered HTML pages when no per-site override is configured.
_DEFAULT_CACHE_TTL_SECONDS: int = 300  # 5 minutes

# Rendered-page cache.  Key: (slug, path_key).  Value: (html, computed_at).
# path_key examples: "index", "browse", "doc:file.xml", "page:about",
# "search:term".
_page_cache: dict[tuple[str, str], tuple[str, datetime]] = {}

# Per-site XSLT transform cache.  Key: slug.  Value: (transform_callable, cached_at).
# Populated on first dynamic request; invalidated by PUT /websites/{slug} or clear-cache.
_site_xslt_cache: dict[str, tuple[Callable[[bytes], str], datetime]] = {}


def _get_cache_ttl(website: Website) -> int:
    """Return the effective cache TTL in seconds for *website*.

    Precedence (highest first):
      1. Per-site override: ``website.theme_config["cache_ttl_seconds"]``
      2. Global hard-coded default (300 s — configurable via system_settings in the future)
    """
    theme_ttl = (website.theme_config or {}).get("cache_ttl_seconds")
    if isinstance(theme_ttl, int) and theme_ttl > 0:
        return theme_ttl
    return _DEFAULT_CACHE_TTL_SECONDS


def _get_cached_page(slug: str, path_key: str, ttl_seconds: int) -> str | None:
    """Return cached HTML for *(slug, path_key)*, or ``None`` if absent / expired."""
    key = (slug, path_key)
    entry = _page_cache.get(key)
    if entry is None:
        return None
    html, computed_at = entry
    if (datetime.now(UTC) - computed_at).total_seconds() > ttl_seconds:
        del _page_cache[key]
        return None
    return html


def _set_cached_page(slug: str, path_key: str, html: str) -> None:
    """Store *html* in the page cache for *(slug, path_key)*."""
    _page_cache[(slug, path_key)] = (html, datetime.now(UTC))


def invalidate_cache(slug: str) -> None:
    """Drop all cached pages and the XSLT transform for *slug*.

    Called automatically by ``update_website()`` and by the
    ``POST /websites/{slug}/clear-cache`` endpoint.
    """
    stale_keys = [k for k in _page_cache if k[0] == slug]
    for k in stale_keys:
        del _page_cache[k]
    _site_xslt_cache.pop(slug, None)
    logger.info("website_cache_invalidated", slug=slug)


async def _resolve_transform_cached(
    slug: str, xslt_config: dict
) -> Callable[[bytes], str]:
    """Return the XSLT transform callable for *slug*, using the per-site cache.

    The transform is cached until ``invalidate_cache(slug)`` is called.
    On first call (or after invalidation), delegates to ``_resolve_transform()``.
    """
    entry = _site_xslt_cache.get(slug)
    if entry is not None:
        transform, _ = entry
        return transform
    transform = await _resolve_transform(xslt_config)
    _site_xslt_cache[slug] = (transform, datetime.now(UTC))
    return transform


def compute_etag(website: Website) -> str:
    """Compute a short ETag for *website* based on slug + last update time.

    Changes whenever ``PUT /websites/{slug}`` is called (which updates
    ``updated_at``).  Suitable for CDN / browser conditional-GET caching.
    """
    raw = f"{website.slug}|{website.updated_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── XSLT cache (same pattern as public_view.py) ───────────────────────────────

_XSLT_PATH = Path(__file__).parent.parent / "xslt" / "tei_generic.xsl"
_xslt_transform: etree.XSLT | None = None


def _get_transform() -> etree.XSLT:
    global _xslt_transform
    if _xslt_transform is None:
        xslt_doc = etree.parse(str(_XSLT_PATH))
        _xslt_transform = etree.XSLT(xslt_doc)
    return _xslt_transform


# ── HTML generation helpers ───────────────────────────────────────────────────

# Static CSS injected into every generated page.
# Theme colours are injected as :root custom properties in the <style> block.
_STATIC_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--font);
  color: var(--text);
  background: var(--bg);
  line-height: 1.7;
  font-size: 1rem;
}
/* ── Navbar ── */
header { background: var(--primary); padding: 0 1.5rem; }
nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 960px;
  margin: 0 auto;
  height: 3.5rem;
}
.brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  color: #fff;
  text-decoration: none;
  font-weight: bold;
  font-size: 1.05rem;
}
.nav-logo {
  height: 2rem;
  width: auto;
  object-fit: contain;
  display: block;
}
.nav-links { display: flex; gap: 1.5rem; align-items: center; }
.nav-links a { color: rgba(255,255,255,0.82); text-decoration: none; font-size: 0.875rem; }
.nav-links a:hover { color: #fff; }
/* ── Hero (cover/index page) ── */
.hero { padding: 4.5rem 0 3.5rem; text-align: center; }
.hero h1 { font-size: 2.5rem; line-height: 1.15; margin-bottom: 1rem; }
.hero .lead {
  font-size: 1.1rem;
  color: #4b5563;
  max-width: 640px;
  margin: 0 auto 1rem;
}
.hero .meta-block { font-size: 0.875rem; color: #6b7280; margin-bottom: 2rem; }
.btn-primary {
  display: inline-block;
  background: var(--primary);
  color: #fff !important;
  padding: 0.7rem 1.75rem;
  border-radius: 0.375rem;
  text-decoration: none;
  font-size: 0.9rem;
  font-family: system-ui, sans-serif;
  letter-spacing: 0.01em;
}
.btn-primary:hover { opacity: 0.88; }
/* ── Home body grid ── */
.home-body { margin-top: 2.5rem; }
.home-grid { display: grid; gap: 2rem; }
.home-grid.layout-single  { grid-template-columns: 1fr; }
.home-grid.layout-two-left  { grid-template-columns: 30fr 70fr; }
.home-grid.layout-two-right { grid-template-columns: 70fr 30fr; }
.home-grid.layout-three  { grid-template-columns: 20fr 60fr 20fr; }
@media (max-width: 640px) { .home-grid { grid-template-columns: 1fr !important; } }
.home-col { min-width: 0; }
.home-col img { max-width: 100%; height: auto; display: block; margin: 1rem 0; border-radius: 0.25rem; }
.home-col a { color: var(--primary); }
.home-col h2 { font-size: 1.25rem; margin: 1.5rem 0 0.5rem; line-height: 1.2; }
.home-col h3 { font-size: 1.05rem; margin: 1.25rem 0 0.4rem; }
.home-col h4 { font-size: 0.95rem; margin: 1rem 0 0.3rem; }
.home-col p  { margin-bottom: 0.9rem; }
.home-col ul { margin: 0.5rem 0 0.9rem 1.25rem; }
.home-col ol { margin: 0.5rem 0 0.9rem 1.25rem; }
.home-col li { margin-bottom: 0.2rem; }
.home-col figure { margin: 1.25rem 0; }
.home-col figcaption { font-size: 0.8rem; color: #6b7280; margin-top: 0.35rem; text-align: center; }
/* ── Content pages ── */
main { max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem; }
h1 { font-size: 1.8rem; margin-bottom: 0.5rem; line-height: 1.2; }
h2 { font-size: 1.25rem; margin: 2rem 0 0.75rem; }
h3 { font-size: 1.05rem; margin: 1.5rem 0 0.5rem; }
p { margin-bottom: 1rem; }
a { color: var(--primary); }
ul { margin: 0.5rem 0 1rem 1.5rem; }
li { margin-bottom: 0.3rem; }
.doc-count { font-size: 0.85rem; color: #6b7280; margin-bottom: 1.5rem; }
.doc-list { list-style: none; margin-left: 0; }
.doc-list li { border-bottom: 1px solid #e5e7eb; padding: 0.75rem 0; }
.doc-list a { font-weight: 500; }
.doc-meta { font-size: 0.85rem; color: #6b7280; margin-top: 0.2rem; }
/* ── Document page — TEI header banner ── */
.tei-header {
  background: var(--doc-banner-bg);
  color: var(--doc-banner-text);
  padding: 1.5rem 1.5rem 1.25rem;
  margin-bottom: 2rem;
  border-radius: 0.375rem;
}
.tei-header .tei-title,
.tei-header .tei-author,
.tei-header .tei-pub { color: var(--doc-banner-text); }
.tei-header .tei-author { opacity: 0.85; font-style: italic; font-size: 0.95rem; margin-top: 0.3rem; }
.tei-header .tei-pub { opacity: 0.7; font-size: 0.8rem; margin-top: 0.2rem; }
.tei-body { padding-top: 0.5rem; }
footer {
  margin-top: 4rem;
  border-top: 1px solid #e5e7eb;
  padding: 1rem 1.5rem;
  text-align: center;
  font-size: 0.78rem;
  color: var(--footer-text);
  background: var(--footer-bg);
}
footer a { color: inherit; text-decoration: underline; }
footer a:hover { opacity: 0.75; }
/* ── Breadcrumb ── */
.breadcrumb { max-width: 960px; margin: 0.75rem auto 0; padding: 0 1.5rem; }
.breadcrumb ol { list-style: none; display: flex; flex-wrap: wrap; gap: 0.25rem; font-size: 0.8rem; color: #6b7280; }
.breadcrumb li + li::before { content: "›"; margin-right: 0.25rem; }
.breadcrumb a { color: #6b7280; text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.breadcrumb [aria-current="page"] { color: #374151; font-weight: 500; }
/* ── Column page-menu widget ── */
.col-page-menu { margin: 0.75rem 0; }
.col-page-menu ul { list-style: none; margin: 0; padding: 0; }
.col-page-menu li { border-bottom: 1px solid #f3f4f6; }
.col-page-menu li:last-child { border-bottom: none; }
.col-page-menu a { display: block; padding: 0.4rem 0.5rem; color: var(--primary); text-decoration: none; font-size: 0.9rem; }
.col-page-menu a:hover { text-decoration: underline; }
/* ── Column index-list widget ── */
.col-index-list { margin: 0.75rem 0; }
.col-index-list ul { list-style: none; margin: 0; padding: 0; }
.col-index-list li { border-bottom: 1px solid #f3f4f6; }
.col-index-list li:last-child { border-bottom: none; }
.col-index-list a { display: block; padding: 0.4rem 0.5rem; color: var(--primary); text-decoration: none; font-size: 0.9rem; }
.col-index-list a:hover { text-decoration: underline; }
/* ── Column search widget ── */
.col-search-widget { margin: 0.75rem 0; }
.col-search-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1.5px solid var(--primary);
  border-radius: 0.375rem;
  font-size: 0.9rem;
  font-family: inherit;
  outline: none;
  color: var(--text);
  background: #fff;
}
.col-search-input:focus { box-shadow: 0 0 0 2px rgba(99,102,241,0.12); }
.col-search-results {
  list-style: none;
  margin: 0.35rem 0 0;
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
}
.col-search-results li { border-bottom: 1px solid #f3f4f6; }
.col-search-results li:last-child { border-bottom: none; }
.col-search-results a {
  display: block;
  padding: 0.4rem 0.75rem;
  font-size: 0.85rem;
  color: var(--text);
  text-decoration: none;
}
.col-search-results a:hover { background: #f9fafb; color: var(--primary); }
/* ── Search page ── */
.search-wrap { max-width: 720px; margin: 0 auto; padding: 2rem 1rem; }
.search-wrap h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: 1.25rem; }
.search-box input[type=search] {
  width: 100%;
  padding: 0.625rem 1rem;
  font-size: 1rem;
  font-family: inherit;
  border: 2px solid #d1d5db;
  border-radius: 0.5rem;
  outline: none;
  background: #fff;
  color: #1e293b;
}
.search-box input[type=search]:focus { border-color: var(--primary); }
.search-count { font-size: 0.8rem; color: #9ca3af; margin: 0.75rem 0 0.25rem; }
.search-hit {
  padding: 0.75rem 0;
  border-bottom: 1px solid #e5e7eb;
}
.search-hit a {
  font-size: 1rem;
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}
.search-hit a:hover { text-decoration: underline; }
.search-hit .hit-author { font-size: 0.8rem; color: #6b7280; margin-top: 0.15rem; }
.search-hit .hit-snippet { font-size: 0.82rem; color: #4b5563; margin-top: 0.25rem; line-height: 1.5; }
mark { background: #fef08a; color: inherit; padding: 0 1px; border-radius: 2px; }
/* ── Index page ── */
.index__title { font-size: 1.8rem; margin-bottom: 1.5rem; }
.index__entries { list-style: none; margin: 0; padding: 0; }
.index__entry { margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid #e5e7eb; }
.index__entry:last-child { border-bottom: none; }
.index__key { font-size: 1.05rem; font-weight: 600; display: block; margin-bottom: 0.5rem; }
.index__subentries { list-style: none; margin: 0.25rem 0 0 1rem; padding: 0; }
.index__subentry { margin-bottom: 0.6rem; }
.index__subkey { font-size: 0.85rem; font-style: italic; color: #6b7280; display: block; margin-bottom: 0.2rem; }
.index__variants { list-style: none; margin: 0 0 0 1rem; padding: 0; }
.index__variant { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.4rem; margin-bottom: 0.15rem; font-size: 0.875rem; }
.index__refs { display: inline-flex; flex-wrap: wrap; gap: 0.3rem; color: #9ca3af; font-size: 0.8rem; }
.index__ref { color: var(--primary); text-decoration: none; }
.index__ref:hover { text-decoration: underline; }
.index__empty { color: #9ca3af; font-style: italic; }
.search-info { font-size: 0.8rem; color: #9ca3af; margin: 0.75rem 0 0.25rem; }
.search-empty { color: #9ca3af; font-style: italic; margin-top: 1rem; }
/* ── Aggregated indices page tabs ── */
.indices-page-title { font-size: 1.8rem; margin-bottom: 1.25rem; }
.indices-tabs-btns { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; }
.indices-tab-btn { background: none; border: 1px solid #e5e7eb; cursor: pointer; padding: 0.4rem 1rem; border-radius: 4px 4px 0 0; font-size: 0.92rem; color: #6b7280; font-family: var(--font); transition: background 0.15s; }
.indices-tab-btn:hover { background: #f3f4f6; color: #1f2937; }
.indices-tab-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.indices-panel { display: none; }
.indices-panel.active { display: block; }
/* ── Index filter ── */
.index__filter { width: 100%; padding: 0.4rem 0.75rem; font-size: 0.9rem; border: 1px solid #d1d5db; border-radius: 4px; margin-bottom: 1rem; font-family: var(--font); }
.index__filter:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px rgba(0,0,0,0.06); }
.index__filter-empty { color: #9ca3af; font-style: italic; font-size: 0.875rem; margin-top: 0.5rem; display: none; }
"""


_DEFAULT_FONT = 'Georgia,"Times New Roman",serif'


def _style_block(theme: dict) -> str:
    primary = _html.escape(theme.get("primary_color", "#1e293b"))
    text = _html.escape(theme.get("text_color", "#1e293b"))
    bg = _html.escape(theme.get("bg_color", "#ffffff"))
    # Banner defaults: same primary as navbar background, white text for contrast
    doc_banner_bg = _html.escape(theme.get("doc_banner_bg", primary))
    doc_banner_text = _html.escape(theme.get("doc_banner_text", "#ffffff"))
    # Font family — sanitize to strip HTML injection chars but keep CSS syntax intact
    font = re.sub(r"[<>&]", "", theme.get("font_family", _DEFAULT_FONT) or _DEFAULT_FONT)
    # Footer colours — fall back to current hard-coded defaults when unset
    footer_bg = _html.escape(theme.get("footer_bg", "transparent") or "transparent")
    footer_color = _html.escape(theme.get("footer_text", "#9ca3af") or "#9ca3af")
    root_vars = (
        f":root{{--primary:{primary};--text:{text};--bg:{bg};"
        f"--doc-banner-bg:{doc_banner_bg};--doc-banner-text:{doc_banner_text};"
        f"--font:{font};--footer-bg:{footer_bg};--footer-text:{footer_color};}}"
    )
    return f"<style>\n{root_vars}\n{_STATIC_CSS}\n</style>"


# Sentinels emitted by widget Tiptap nodes (renderHTML output).
_WIDGET_TAG_SEARCH_BAR = '<div data-widget="search-bar"></div>'
_WIDGET_TAG_PAGE_MENU  = '<div data-widget="page-menu"></div>'
_WIDGET_TAG_INDEX_LIST = '<div data-widget="index-list"></div>'


def _build_search_widget_html(site_base_url: str = "") -> str:
    """Return HTML for the search-bar column widget.

    Both STATIC and DYNAMIC/HYBRID render a plain form.  The action URL differs:
    - STATIC: ``search.html`` (relative, root-level page)
    - DYNAMIC/HYBRID: absolute server-side endpoint (site_base_url set)
    """
    if site_base_url:
        action = _html.escape(f"{site_base_url}/search")
    else:
        action = "search.html"
    return (
        '<div class="col-search-widget">'
        f'<form action="{action}" method="get">'
        '<input type="search" name="q" class="col-search-input"'
        ' placeholder="Search documents\u2026"'
        ' aria-label="Search documents" />'
        "</form>"
        "</div>"
    )


def _build_page_menu_html(
    pages: list[WebsitePage],
    nav_config: list | None = None,
    site_base_url: str = "",
) -> str:
    """Return HTML for the page-menu column widget.

    Renders a nav list of all visible pages (system + free) sorted by global
    sort_order, excluding Home (the widget lives on the home page itself).

    When *site_base_url* is empty (static mode) paths are relative to the site
    root (index.html lives there).  When set (dynamic/hybrid mode), absolute
    URLs rooted at *site_base_url* are used instead.
    """
    menu_items: list[tuple[int, str]] = []

    # System pages — Browse and Search (Home is excluded: this widget is on index.html)
    for ap in _parse_aracne_nav(nav_config or []):
        if ap.get("is_hidden") or ap["id"] == "home":
            continue
        so = int(ap["sort_order"])
        pid = ap["id"]
        if pid == "browse":
            href = f"{site_base_url}/browse" if site_base_url else "browse.html"
            menu_items.append((so, f'<li><a href="{href}">Browse</a></li>'))
        elif pid == "search":
            href = f"{site_base_url}/search" if site_base_url else "search.html"
            menu_items.append((so, f'<li><a href="{href}">Search</a></li>'))

    # Free pages (already filtered for visibility)
    for p in pages:
        if site_base_url:
            href = f"{site_base_url}/pages/{_html.escape(p.slug)}"
        else:
            href = f"pages/{_html.escape(p.slug)}.html"
        menu_items.append(
            (p.sort_order, f'<li><a href="{href}">{_html.escape(p.title)}</a></li>')
        )

    if not menu_items:
        return ""

    menu_items.sort(key=lambda x: x[0])
    items = "".join(html for _, html in menu_items)
    return f'<nav class="col-page-menu"><ul>{items}</ul></nav>'


def _build_index_list_widget_html(
    indices: list[WebsiteIndex] | None = None,
    nav_config: list | None = None,
    site_base_url: str = "",
) -> str:
    """Return HTML for the index-list column widget.

    Renders a nav list of built indices.  Only indices with *cached_data* (i.e.
    already built) are shown — unbuilt indices would produce dead links.

    Link targets follow the same static/dynamic split as other widgets:
    - STATIC: ``indices.html`` (all indices on a single tabbed page)
    - DYNAMIC/HYBRID: ``{site_base_url}/indices/{label}`` (per-index route)

    The widget is hidden (returns ``""``) when the "indices" system page is
    hidden via *nav_config* or when no index has been built yet.
    """
    # Check whether the indices system page is hidden.
    nav_map = {ap["id"]: ap for ap in _parse_aracne_nav(nav_config or [])}
    if nav_map.get("indices", {}).get("is_hidden"):
        return ""

    built = [idx for idx in (indices or []) if idx.cached_data is not None]
    if not built:
        return ""

    items_html = ""
    for idx in built:
        label_escaped = _html.escape(idx.label)
        title_escaped = _html.escape(idx.title)
        if site_base_url:
            href = f"{site_base_url}/indices/{label_escaped}"
        else:
            href = f"indices.html#{label_escaped}"
        items_html += f'<li><a href="{href}">{title_escaped}</a></li>'

    return f'<nav class="col-index-list"><ul>{items_html}</ul></nav>'


def _render_col_content(
    text: str,
    pages: list[WebsitePage] | None = None,
    nav_config: list | None = None,
    site_base_url: str = "",
    indices: list[WebsiteIndex] | None = None,
) -> str:
    """Return column body HTML for embedding in the page.

    If *text* looks like HTML (starts with a tag — Tiptap output) it is
    returned as-is after expanding any widget placeholders.  Otherwise it is
    treated as lightweight Markdown so that content written before the WYSIWYG
    editor was introduced still renders correctly.

    Both paths are trusted Designer+ input written for their own static site;
    no html.escape is applied.

    *site_base_url*: when set, widget links use absolute dynamic URLs instead
    of relative static paths.
    """
    stripped = text.strip()
    if not stripped:
        return ""
    # HTML passthrough: Tiptap always produces output starting with a tag.
    if stripped.startswith("<"):
        result = stripped.replace(
            _WIDGET_TAG_SEARCH_BAR,
            _build_search_widget_html(site_base_url),
        )
        result = result.replace(
            _WIDGET_TAG_PAGE_MENU,
            _build_page_menu_html(pages or [], nav_config, site_base_url),
        )
        result = result.replace(
            _WIDGET_TAG_INDEX_LIST,
            _build_index_list_widget_html(indices, nav_config, site_base_url),
        )
        return result
    # Markdown fallback (legacy / plain-text content)
    return _md_col_to_html(stripped)


def _md_col_to_html(text: str) -> str:
    """Lightweight Markdown → HTML for column content (legacy/fallback path)."""
    import re as _re

    def inline(s: str) -> str:
        s = _re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">',
            s,
        )
        s = _re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
            s,
        )
        s = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        s = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', s)
        return s

    lines = text.splitlines()
    blocks: list[str] = []
    para_lines: list[str] = []

    def flush() -> None:
        if para_lines:
            blocks.append(f"<p>{' '.join(inline(l) for l in para_lines)}</p>")
            para_lines.clear()

    for line in lines:
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("### "):
            flush(); blocks.append(f"<h4>{inline(s[4:])}</h4>")
        elif s.startswith("## "):
            flush(); blocks.append(f"<h3>{inline(s[3:])}</h3>")
        elif s.startswith("# "):
            flush(); blocks.append(f"<h2>{inline(s[2:])}</h2>")
        elif s.startswith("<"):
            flush(); blocks.append(s)
        else:
            para_lines.append(s)

    flush()
    return "\n".join(blocks)


def _parse_aracne_nav(nav_config: list) -> list[dict]:
    """Return the ordered Aracne system-page descriptors from *nav_config*.

    Fills in defaults for any missing entry so the caller always receives
    exactly four records: home (always first), then browse, search, and
    indices sorted by their stored ``sort_order``.
    """
    _defaults: dict[str, dict] = {
        "home":    {"id": "home",    "sort_order": 0, "is_hidden": False},
        "browse":  {"id": "browse",  "sort_order": 1, "is_hidden": False},
        "search":  {"id": "search",  "sort_order": 2, "is_hidden": False},
        "indices": {"id": "indices", "sort_order": 3, "is_hidden": False},
    }
    merged: dict[str, dict] = {}
    for page_id, default in _defaults.items():
        saved = next((p for p in nav_config if isinstance(p, dict) and p.get("id") == page_id), None)
        merged[page_id] = {**default, **(saved or {})}

    rest = sorted(
        [merged["browse"], merged["search"], merged["indices"]],
        key=lambda p: p["sort_order"],
    )
    return [merged["home"], *rest]


def _render_navbar(
    *,
    site_title: str,
    logo_url: str | None,
    pages: list[WebsitePage],
    path_prefix: str = "",
    nav_config: list | None = None,
    site_base_url: str = "",
    indices: list | None = None,
) -> str:
    """Build the <header><nav> block.

    Static mode (site_base_url=""): path_prefix must be "" for root-level pages
    (index.html, browse.html) and "../" for pages in subdirectories (docs/, pages/).

    Dynamic/Hybrid mode (site_base_url set): all hrefs are absolute paths rooted
    at site_base_url; path_prefix is ignored.

    nav_config controls visibility and order of Browse / Search links.
    """
    logo_html = ""
    if logo_url:
        esc_logo = _html.escape(logo_url)
        logo_html = f'<img src="{esc_logo}" alt="" class="nav-logo">'

    if site_base_url:
        home_href = f"{site_base_url}/"
        browse_href = f"{site_base_url}/browse"
        search_href = f"{site_base_url}/search"
    else:
        home_href = f"{path_prefix}index.html"
        browse_href = f"{path_prefix}browse.html"
        search_href = f"{path_prefix}search.html"

    # Merge system links and free-page links into a single list sorted by the
    # global sort_order (system pages from nav_config, free pages from sort_order).
    nav_items: list[tuple[int, str]] = []

    for ap in _parse_aracne_nav(nav_config or []):
        if ap.get("is_hidden"):
            continue
        so = int(ap["sort_order"])
        pid = ap["id"]
        if pid == "home":
            nav_items.append((so, f'<a href="{home_href}">Home</a>'))
        elif pid == "browse":
            nav_items.append((so, f'<a href="{browse_href}">Browse</a>'))
        elif pid == "search":
            nav_items.append((so, f'<a href="{search_href}">Search</a>'))
        elif pid == "indices":
            # Show a single "Indices" link only when at least one index has been built.
            has_built = any(idx.last_built_at for idx in (indices or []))
            if has_built:
                if site_base_url:
                    indices_href = f"{site_base_url}/indices/"
                else:
                    indices_href = f"{path_prefix}indices.html"
                nav_items.append((so, f'<a href="{indices_href}">Indices</a>'))

    for page in pages:  # already filtered for visibility
        if site_base_url:
            href = f"{site_base_url}/pages/{_html.escape(page.slug)}"
        else:
            href = f"{path_prefix}pages/{_html.escape(page.slug)}.html"
        nav_items.append((page.sort_order, f'<a href="{href}">{_html.escape(page.title)}</a>'))

    nav_items.sort(key=lambda x: x[0])
    links_html = "".join(link for _, link in nav_items)

    return f"""<header>
    <nav>
      <a class="brand" href="{home_href}">{logo_html}<span>{_html.escape(site_title)}</span></a>
      <div class="nav-links">
        {links_html}
      </div>
    </nav>
  </header>"""


def _emit_meta(lines: list[str], name: str, raw: str | list | None) -> None:
    """Append one ``<meta>`` tag per non-empty value.

    ``raw`` may be a plain string or a list of strings (repeatable fields).
    """
    if raw is None:
        return
    values: list[str] = raw if isinstance(raw, list) else [raw]
    for item in values:
        v = str(item).strip()
        if v:
            lines.append(f'  <meta name="{name}" content="{_html.escape(v)}">')


def _build_meta_tags(meta: dict) -> str:
    """Build HTML <meta> tag strings from a meta_config dict.

    Standard HTML meta tags and Dublin Core (DC.*) are emitted only for
    non-empty values.  The DC namespace <link> is prepended automatically
    when at least one DC field has a value.  Repeatable fields may be stored
    as either a plain string or a list of strings.
    """
    if not meta:
        return ""

    lines: list[str] = []

    _html_fields = [
        ("keywords",    "keywords"),
        ("description", "description"),
        ("subject",     "subject"),
        ("copyright",   "copyright"),
        ("author",      "author"),
        ("designer",    "designer"),
        ("url",         "url"),
    ]
    for key, name in _html_fields:
        _emit_meta(lines, name, meta.get(key))

    _dc_fields = [
        ("dc_title",       "DC.Title"),
        ("dc_creator",     "DC.Creator"),
        ("dc_subject",     "DC.Subject"),
        ("dc_description", "DC.Description"),
        ("dc_publisher",   "DC.Publisher"),
        ("dc_contributor", "DC.Contributor"),
        ("dc_date",        "DC.Date"),
        ("dc_type",        "DC.Type"),
        ("dc_format",      "DC.Format"),
        ("dc_identifier",  "DC.Identifier"),
    ]
    dc_lines: list[str] = []
    for key, name in _dc_fields:
        _emit_meta(dc_lines, name, meta.get(key))
    if dc_lines:
        lines.append('  <link rel="schema.DC" href="http://purl.org/dc/elements/1.1/" />')
        lines.extend(dc_lines)

    return "\n".join(lines)


def _identifier_label(url: str) -> str:
    """Return a short human-readable label for a persistent identifier URL."""
    lower = url.lower()
    if "doi.org" in lower:
        return "DOI"
    if "hdl.handle.net" in lower or "handle.net" in lower:
        return "Handle"
    if "urn:" in lower:
        return "URN"
    return "Identifier"


def _render_breadcrumb(crumbs: list[tuple[str | None, str]]) -> str:
    """Build a semantic breadcrumb nav element.

    Args:
        crumbs: Sequence of (url, label) pairs. url=None for the current (last) crumb,
                which receives aria-current="page" and no anchor element.
    """
    items: list[str] = []
    for url, label in crumbs:
        esc_label = _html.escape(label)
        if url is None:
            items.append(f'<li aria-current="page">{esc_label}</li>')
        else:
            esc_url = _html.escape(url)
            items.append(f'<li><a href="{esc_url}">{esc_label}</a></li>')
    return f'<nav class="breadcrumb" aria-label="Breadcrumb"><ol>{"".join(items)}</ol></nav>'


# Inline script injected into every generated page.
# When the URL carries a ?_preview=TOKEN (used to let staff browse unpublished
# sites from a browser tab / iframe that cannot send an Authorization header),
# this snippet propagates the token to every local <a href> on the page and
# watches the DOM for dynamically inserted links (e.g. search results).
_PREVIEW_PROPAGATOR_SCRIPT = (
    '<script>(function(){'
    'var m=location.search.match(/[?&]_preview=([^&]+)/);'
    'if(!m)return;'
    'var t=m[1];'
    'function patch(a){'
    'var h=a.getAttribute("href");'
    'if(!h||/^(https?:|\\/\\/|mailto:|#)/.test(h)||h.indexOf("_preview=")!==-1)return;'
    'a.setAttribute("href",h+(h.indexOf("?")!==-1?"&":"?")+"_preview="+t);}'
    'document.querySelectorAll("a[href]").forEach(patch);'
    'new MutationObserver(function(ms){'
    'ms.forEach(function(m){'
    'm.addedNodes.forEach(function(n){'
    'if(n.querySelectorAll)n.querySelectorAll("a[href]").forEach(patch);'
    '});});}).observe(document.body,{childList:true,subtree:true});'
    '})();</script>'
)

# Inline script that reads ?highlight=TERM from the URL and highlights all
# occurrences of that term in the page content using <mark> elements.
# Uses TreeWalker to operate on text nodes only (never breaks existing markup).
# Scrolls smoothly to the first match after highlighting.
_HIGHLIGHT_SCRIPT = (
    '<script>(function(){'
    'var m=location.search.match(/[?&]highlight=([^&]+)/);'
    'if(!m)return;'
    'var term=decodeURIComponent(m[1].replace(/\\+/g," ")).trim();'
    'if(!term)return;'
    'var root=document.querySelector(".tei-body")||document.querySelector("main");'
    'if(!root)return;'
    'function esc(s){return s.replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&");}'
    'var re=new RegExp("("+esc(term)+")","gi");'
    'var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,null,false);'
    'var nodes=[];'
    'var n;'
    'while((n=tw.nextNode())){'
    'if(/^(script|style|mark)$/i.test(n.parentNode.nodeName))continue;'
    'if(re.test(n.textContent))nodes.push(n);'
    're.lastIndex=0;'
    '}'
    'nodes.forEach(function(tn){'
    'var parts=tn.textContent.split(re);'
    'if(parts.length<2)return;'
    'var frag=document.createDocumentFragment();'
    'parts.forEach(function(p,i){'
    'if(i%2===1){var mk=document.createElement("mark");mk.textContent=p;frag.appendChild(mk);}'
    'else if(p)frag.appendChild(document.createTextNode(p));'
    '});'
    'tn.parentNode.replaceChild(frag,tn);'
    '});'
    'var first=root.querySelector("mark");'
    'if(first)first.scrollIntoView({behavior:"smooth",block:"center"});'
    '})();</script>'
)


def _render_page(
    *,
    site_title: str,
    page_title: str,
    content: str,
    style: str,
    navbar: str,
    breadcrumb: str = "",
    footer_note: str = "",
    identifier_url: str = "",
    meta_tags: str = "",
) -> str:
    esc_site = _html.escape(site_title)
    esc_page = _html.escape(page_title)
    footer_extra = f'<span class="footer-publisher">{footer_note}</span> · ' if footer_note else ""
    if identifier_url:
        label = _identifier_label(identifier_url)
        esc_url = _html.escape(identifier_url)
        footer_extra += f'<a href="{esc_url}" class="footer-identifier" target="_blank" rel="noopener">{label}</a> · '
    meta_block = f"\n{meta_tags}" if meta_tags else ""
    breadcrumb_block = f"\n  {breadcrumb}" if breadcrumb else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc_page} — {esc_site}</title>{meta_block}
  {style}
</head>
<body>
  {navbar}{breadcrumb_block}
  <main>
    {content}
  </main>
  <footer>{footer_extra}Built with <a href="https://github.com/orazio-nelson/aracne2">Aracne2</a></footer>
  {_PREVIEW_PROPAGATOR_SCRIPT}
  {_HIGHLIGHT_SCRIPT}
</body>
</html>"""


def _md_to_html(content_md: str) -> str:
    """Convert page body to HTML.

    If the content starts with an HTML tag (Tiptap WYSIWYG output) it is
    returned as-is.  Otherwise the legacy Markdown path applies.
    """
    stripped = content_md.strip()
    if not stripped:
        return ""
    if stripped.startswith("<"):
        return stripped
    # Legacy Markdown
    lines = stripped.splitlines()
    blocks: list[str] = []
    para_lines: list[str] = []

    def flush_para() -> None:
        if para_lines:
            blocks.append(f"<p>{'<br>'.join(_html.escape(l) for l in para_lines)}</p>")
            para_lines.clear()

    for line in lines:
        s = line.strip()
        if not s:
            flush_para()
        elif s.startswith("### "):
            flush_para(); blocks.append(f"<h3>{_html.escape(s[4:])}</h3>")
        elif s.startswith("## "):
            flush_para(); blocks.append(f"<h2>{_html.escape(s[3:])}</h2>")
        elif s.startswith("# "):
            flush_para(); blocks.append(f"<h2>{_html.escape(s[2:])}</h2>")
        else:
            para_lines.append(s)

    flush_para()
    return "\n".join(blocks)


def _render_xml_to_html(xml_bytes: bytes) -> str:
    """Apply the generic TEI XSLT and return the <body> inner HTML."""
    transform = _get_transform()
    xml_doc = etree.fromstring(xml_bytes)  # noqa: S320 — from our own eXist-db
    result = transform(xml_doc)
    result_str = str(result)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", result_str, re.DOTALL | re.IGNORECASE)
    return body_match.group(1) if body_match else result_str


async def _resolve_transform(
    xslt_config: dict,
) -> Callable[[bytes], str]:
    """Return a synchronous transform callable from *xslt_config*.

    The callable is suitable for use inside ``asyncio.to_thread()``.
    Falls back to the built-in generic transform when no valid XSLT source
    is configured.

    Supported sources:
      "default"  — built-in generic TEI transform (``tei_generic.xsl``).
      "custom"   — inline XSLT text stored in ``xslt_config["content"]``.
      "url"      — XSLT fetched from ``xslt_config["url"]`` at build time.
      "catalog"  — XSLT loaded from the xslt_templates catalog by
                   ``xslt_config["catalog_id"]`` (UUID string).
    """
    from app.models.xslt_template import XsltTemplate

    source = xslt_config.get("source", "default")
    processor = str(xslt_config.get("processor", "lxml"))

    if source == "custom":
        content = (xslt_config.get("content") or "").strip()
        if content:
            def _custom(xml_bytes: bytes, _c: str = content, _p: str = processor) -> str:
                return apply_xslt(_c, xml_bytes, _p)
            return _custom

    elif source == "url":
        url = (xslt_config.get("url") or "").strip()
        if url:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.text
            def _from_url(xml_bytes: bytes, _c: str = content, _p: str = processor) -> str:
                return apply_xslt(_c, xml_bytes, _p)
            return _from_url

    elif source == "catalog":
        raw_id = (xslt_config.get("catalog_id") or "").strip()
        if raw_id:
            import uuid as _uuid
            try:
                catalog_id = _uuid.UUID(raw_id)
            except ValueError:
                logger.warning("xslt_resolve_invalid_catalog_id", catalog_id=raw_id)
            else:
                from app.db.postgres import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    tpl: XsltTemplate | None = await db.get(XsltTemplate, catalog_id)
                if tpl is not None:
                    content = tpl.content
                    proc = tpl.processor
                    def _from_catalog(xml_bytes: bytes, _c: str = content, _p: str = proc) -> str:
                        return apply_xslt(_c, xml_bytes, _p)
                    return _from_catalog
                logger.warning("xslt_resolve_catalog_not_found", catalog_id=raw_id)

    return _render_xml_to_html


def _build_cover_content(
    *,
    website_title: str,
    col: Collection | None,
    doc_count: int,
    theme: dict,
    pages: list[WebsitePage] | None = None,
    nav_config: list | None = None,
    site_base_url: str = "",
    indices: list[WebsiteIndex] | None = None,
) -> str:
    """Return the hero/cover HTML for index.html.

    Publisher / year are intentionally omitted here — they appear in the footer.
    Below the hero, an optional column grid is rendered from theme_config keys:
      home_layout : "single" | "two_left" | "two_right" | "three"
      col_left    : body text for left sidebar column
      col_center  : body text for central column (shown in all layouts)
      col_right   : body text for right sidebar column

    *site_base_url*: when set (dynamic/hybrid mode), the CTA "Browse" link and
    column-widget hrefs use absolute paths; otherwise relative static paths.
    *indices*: passed through to widget renderers so the index-list widget can
    enumerate built indices.
    """
    title = _html.escape(col.title if col else website_title)
    lead = ""
    if col and col.description:
        lead = f'<p class="lead">{_html.escape(col.description)}</p>'

    author_block = ""
    if col and col.author:
        author_block = f'<p class="meta-block">{_html.escape(col.author)}</p>'

    browse_label = f"Browse {doc_count} document{'s' if doc_count != 1 else ''} →"
    browse_href = f"{site_base_url}/browse" if site_base_url else "browse.html"
    cta = f'<a href="{browse_href}" class="btn-primary">{browse_label}</a>'

    hero = f"""<div class="hero">
  <h1>{title}</h1>
  {lead}
  {author_block}
  {cta}
</div>"""

    # ── Column body grid ──────────────────────────────────────────────────
    layout = theme.get("home_layout", "single")
    center = _render_col_content(
        theme.get("col_center", "") or "", pages, nav_config, site_base_url, indices
    )
    left = _render_col_content(
        theme.get("col_left", "") or "", pages, nav_config, site_base_url, indices
    )
    right = _render_col_content(
        theme.get("col_right", "") or "", pages, nav_config, site_base_url, indices
    )

    if layout == "two_left":
        cols = (
            f'<div class="home-col">{left}</div>'
            f'<div class="home-col">{center}</div>'
        )
        css_class = "layout-two-left"
    elif layout == "two_right":
        cols = (
            f'<div class="home-col">{center}</div>'
            f'<div class="home-col">{right}</div>'
        )
        css_class = "layout-two-right"
    elif layout == "three":
        cols = (
            f'<div class="home-col">{left}</div>'
            f'<div class="home-col">{center}</div>'
            f'<div class="home-col">{right}</div>'
        )
        css_class = "layout-three"
    else:
        cols = f'<div class="home-col">{center}</div>'
        css_class = "layout-single"

    grid = ""
    if center or left or right:
        grid = f'<div class="home-body"><div class="home-grid {css_class}">{cols}</div></div>'

    return hero + grid


def _build_browse_content(docs: list[dict], site_base_url: str = "") -> str:
    """Return the document list HTML for browse.html / dynamic browse page.

    *site_base_url*: when set (dynamic/hybrid mode) doc links use absolute paths;
    otherwise relative static paths with .html extension.
    """
    count = len(docs)
    items = ""
    for doc in docs:
        filename = _html.escape(doc["filename"])
        label = _html.escape(doc.get("title") or doc["filename"])
        author_line = (
            f'<div class="doc-meta">{_html.escape(doc["author"])}</div>'
            if doc.get("author")
            else ""
        )
        if site_base_url:
            href = f"{site_base_url}/docs/{filename}"
        else:
            href = f"docs/{filename}.html"
        items += f'<li><a href="{href}">{label}</a>{author_line}</li>\n'

    return f"""<h1>Documents</h1>
<p class="doc-count">{count} document{'s' if count != 1 else ''}</p>
<ul class="doc-list">
{items}
</ul>"""


def _extract_plain_text(xml_bytes: bytes) -> str:
    """Return all text node content from *xml_bytes* as a single normalised string.

    Used to populate the ``body`` field in the full-text search index.
    Returns an empty string on any parse error.
    """
    import defusedxml.ElementTree as ET  # noqa: PLC0415

    try:
        root = ET.fromstring(xml_bytes)
        return " ".join(" ".join(root.itertext()).split())
    except Exception:
        return ""


def _build_search_content() -> str:
    """Return the search page HTML with inline full-text client-side search.

    The page fetches search.json (pre-built at the site root), which includes
    the plain-text ``body`` of each document.  Search runs entirely in the
    browser — AND-matching across title, author, and full body text, with
    highlighted context snippets.  No external libraries required.
    """
    return """<div class="search-wrap">
  <h1>Search</h1>
  <div class="search-box">
    <input type="search" id="q" placeholder="Search documents\u2026" autocomplete="off" autofocus>
  </div>
  <p class="search-info" id="info"></p>
  <div id="results"></div>
  <noscript>
    <p>JavaScript is required for search. <a href="browse.html">Browse all documents</a>.</p>
  </noscript>
</div>
<script>
(function () {
  'use strict';
  var input   = document.getElementById('q');
  var results = document.getElementById('results');
  var infoEl  = document.getElementById('info');
  var corpus  = null;

  function esc(s) {
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function tokenize(s) {
    return s.toLowerCase().replace(/[^\\w\\s]/g,' ').split(/\\s+/).filter(Boolean);
  }

  /* Return a ~200-char snippet from text with the first matched term highlighted. */
  function snippet(text, terms) {
    var lower = text.toLowerCase();
    var best = -1, bestLen = 0;
    terms.forEach(function(t) {
      var p = lower.indexOf(t);
      if (p !== -1 && (best === -1 || p < best)) { best = p; bestLen = t.length; }
    });
    var CTX = 100;
    if (best === -1) {
      var head = text.slice(0, CTX * 2).replace(/\\s+/g,' ').trim();
      return esc(head) + (text.length > CTX * 2 ? '\u2026' : '');
    }
    var s0 = Math.max(0, best - CTX);
    var s1 = Math.min(text.length, best + bestLen + CTX);
    return (s0 > 0 ? '\u2026' : '') +
           esc(text.slice(s0, best).replace(/\\s+/g,' ')) +
           '<mark>' + esc(text.slice(best, best + bestLen)) + '</mark>' +
           esc(text.slice(best + bestLen, s1).replace(/\\s+/g,' ')) +
           (s1 < text.length ? '\u2026' : '');
  }

  function doSearch(query) {
    var terms = tokenize(query);
    if (!terms.length || corpus === null) {
      infoEl.textContent = '';
      results.innerHTML = '';
      return;
    }
    var hits = corpus.filter(function(d) {
      var hay = ((d.title||'') + ' ' + (d.author||'') + ' ' + (d.body||'')).toLowerCase();
      return terms.every(function(t) { return hay.indexOf(t) !== -1; });
    });
    infoEl.textContent = hits.length + ' result' + (hits.length !== 1 ? 's' : '');
    if (!hits.length) {
      results.innerHTML = '<p class="search-empty">No results found.</p>';
      return;
    }
    var hlParam = query.trim() ? '?highlight=' + encodeURIComponent(query.trim()) : '';
    results.innerHTML = hits.map(function(d) {
      var snip = d.body ? snippet(d.body, terms) : '';
      return '<div class="search-hit">' +
        '<a href="' + esc(d.url) + hlParam + '">' + esc(d.title || d.filename) + '</a>' +
        (d.author ? '<div class="hit-author">' + esc(d.author) + '</div>' : '') +
        (snip     ? '<div class="hit-snippet">' + snip + '</div>'         : '') +
        '</div>';
    }).join('');
  }

  /* Load the gzip-compressed index and decompress natively via DecompressionStream.
     Falls back to a clear message on browsers that do not support the API
     (Chrome < 80, Firefox < 113, Safari < 16.4). */
  if (typeof DecompressionStream === 'undefined') {
    results.innerHTML = '<p class="search-empty">Search requires a modern browser (Chrome 80+, Firefox 113+, Safari 16.4+).</p>';
  } else {
    fetch('search.json.gz')
      .then(function(res) {
        var ds = new DecompressionStream('gzip');
        return new Response(res.body.pipeThrough(ds)).json();
      })
      .then(function(data) { corpus = data; doSearch(input.value); })
      .catch(function() {
        results.innerHTML = '<p class="search-empty">Search index not available.</p>';
      });
  }

  input.addEventListener('input', function() { doSearch(this.value); });

  /* Pre-fill input from URL ?q= parameter (sidebar form navigation). */
  var init = new URLSearchParams(window.location.search).get('q') || '';
  if (init) { input.value = init; }
})();
</script>"""


# ── XSLT preview ──────────────────────────────────────────────────────────────

async def preview_document(
    db: AsyncSession,
    slug: str,
    filename: str,
    xslt_config_override: dict | None = None,
) -> str:
    """Apply XSLT to a single document and return the body HTML fragment.

    Used by the admin Document tab to preview rendering before a full build.
    If *xslt_config_override* is provided, it takes precedence over the
    website's saved xslt_config (allows previewing unsaved stylesheet changes).
    """
    website = await _get_website(db, slug)
    if website.collection_id is None:
        raise NotFoundError("Website has no linked collection.")

    col: Collection | None = await db.get(Collection, website.collection_id)
    if col is None:
        raise NotFoundError("Linked collection not found.")

    xml_bytes = await existdb_client.get_document(col.slug, filename)

    config: dict = (
        xslt_config_override
        if xslt_config_override is not None
        else (website.xslt_config or {})
    )
    xslt_transform = await _resolve_transform(config)
    doc_body: str = await asyncio.to_thread(xslt_transform, xml_bytes)
    return doc_body


# ── Dynamic / Hybrid rendering ────────────────────────────────────────────────

def _build_dynamic_search_content(
    hits: list[dict],
    q: str,
    site_base_url: str,
) -> str:
    """Build the server-rendered search results page content.

    *hits* is a list of dicts with keys: filename, score, kwic.
    When *q* is empty the page shows the search form with no results section.
    """
    esc_q = _html.escape(q)
    esc_action = _html.escape(f"{site_base_url}/search")
    search_form = (
        '<div class="search-wrap">'
        "<h1>Search</h1>"
        '<div class="search-box">'
        f'<form action="{esc_action}" method="get">'
        f'<input type="search" name="q" value="{esc_q}"'
        ' placeholder="Search documents\u2026" autocomplete="off" autofocus>'
        "</form>"
        "</div>"
    )

    if not q:
        return search_form + "</div>"

    if not hits:
        count_line = '<p class="search-count">No results found.</p>'
        return search_form + count_line + "</div>"

    count_line = (
        f'<p class="search-count">{len(hits)} result'
        f'{"s" if len(hits) != 1 else ""} for <em>{esc_q}</em></p>'
    )
    from urllib.parse import quote as _q
    hl_param = f"?highlight={_q(q, safe='')}"
    items = ""
    for hit in hits:
        filename = _html.escape(hit["filename"])
        kwic = _html.escape(hit.get("kwic") or "")
        doc_href = _html.escape(f"{site_base_url}/docs/{hit['filename']}{hl_param}")
        items += (
            '<div class="search-hit">'
            f'<a href="{doc_href}">{filename}</a>'
            + (f'<div class="hit-kwic">{kwic}</div>' if kwic else "")
            + "</div>\n"
        )
    return search_form + count_line + items + "</div>"


async def _fetch_doc_infos(col: Collection) -> list[dict]:
    """Return a list of {filename, title, author} dicts for *col*.

    Tries the title-aware XQuery first; falls back to a plain listing on error.
    """
    import defusedxml.ElementTree as ET

    col_path = existdb_client.col_path(col.slug)
    try:
        raw = await existdb_client.xquery(
            "collections/list_with_titles.xq",
            variables={"collection_path": col_path},
        )
        root_el = ET.fromstring(raw)
        return [
            {
                "filename": (el.findtext("filename") or "").strip(),
                "title": (el.findtext("title") or "").strip() or None,
                "author": (el.findtext("author") or "").strip() or None,
            }
            for el in root_el.findall("doc")
            if (el.findtext("filename") or "").strip()
        ]
    except Exception as exc:
        logger.warning("dynamic_list_docs_failed", col=col.slug, error=str(exc))
        try:
            filenames = await existdb_client.list_collection(col.slug)
            return [{"filename": f, "title": None, "author": None} for f in filenames]
        except Exception:
            return []


async def render_dynamic_index(db: AsyncSession, website: Website) -> str:
    """Render the index/cover page for a DYNAMIC website.

    Results are cached with the website's effective TTL.
    """
    ttl = _get_cache_ttl(website)
    cached = _get_cached_page(website.slug, "index", ttl)
    if cached is not None:
        return cached

    col: Collection | None = (
        await db.get(Collection, website.collection_id)
        if website.collection_id else None
    )
    doc_infos = await _fetch_doc_infos(col) if col else []

    theme = website.theme_config or {}
    base = f"/api/v1/sites/{website.slug}"
    visible_pages = [p for p in website.pages if not p.is_hidden]
    hide_header: bool = bool(theme.get("hide_header", False))

    navbar = "" if hide_header else _render_navbar(
        site_title=website.title,
        logo_url=theme.get("logo_url") or None,
        pages=visible_pages,
        nav_config=website.nav_config or [],
        site_base_url=base,
        indices=website.indices,
    )
    content = _build_cover_content(
        website_title=website.title,
        col=col,
        doc_count=len(doc_infos),
        theme=theme,
        pages=visible_pages,
        nav_config=website.nav_config or [],
        site_base_url=base,
        indices=website.indices,
    )
    footer_note, identifier_url = _footer_parts(col)
    html = _render_page(
        site_title=website.title,
        page_title=website.title,
        content=content,
        style=_style_block(theme),
        navbar=navbar,
        footer_note=footer_note,
        identifier_url=identifier_url,
        meta_tags=_build_meta_tags(website.meta_config or {}),
    )
    _set_cached_page(website.slug, "index", html)
    return html


async def render_dynamic_browse(db: AsyncSession, website: Website) -> str:
    """Render the document-list page for a DYNAMIC website."""
    ttl = _get_cache_ttl(website)
    cached = _get_cached_page(website.slug, "browse", ttl)
    if cached is not None:
        return cached

    col: Collection | None = (
        await db.get(Collection, website.collection_id)
        if website.collection_id else None
    )
    doc_infos = await _fetch_doc_infos(col) if col else []

    theme = website.theme_config or {}
    base = f"/api/v1/sites/{website.slug}"
    visible_pages = [p for p in website.pages if not p.is_hidden]
    hide_header: bool = bool(theme.get("hide_header", False))

    navbar = "" if hide_header else _render_navbar(
        site_title=website.title,
        logo_url=theme.get("logo_url") or None,
        pages=visible_pages,
        nav_config=website.nav_config or [],
        site_base_url=base,
        indices=website.indices,
    )
    footer_note, identifier_url = _footer_parts(col)
    html = _render_page(
        site_title=website.title,
        page_title="Browse",
        content=_build_browse_content(doc_infos, site_base_url=base),
        style=_style_block(theme),
        navbar=navbar,
        breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, "Browse")]),
        footer_note=footer_note,
        identifier_url=identifier_url,
        meta_tags=_build_meta_tags(website.meta_config or {}),
    )
    _set_cached_page(website.slug, "browse", html)
    return html


async def render_dynamic_search(
    db: AsyncSession, website: Website, q: str
) -> str:
    """Render the server-side full-text search results page for a DYNAMIC website.

    Uses eXist-db Lucene ft:query() with a contains() fallback.
    An empty *q* returns a bare search form (no results run).
    """
    import defusedxml.ElementTree as ET

    path_key = f"search:{q}"
    if q:  # cache search results; never cache empty form
        ttl = _get_cache_ttl(website)
        cached = _get_cached_page(website.slug, path_key, ttl)
        if cached is not None:
            return cached

    hits: list[dict] = []
    if q and website.collection_id is not None:
        col: Collection | None = await db.get(Collection, website.collection_id)
        if col is not None:
            try:
                raw = await existdb_client.xquery(
                    "search/fulltext_search.xq",
                    variables={
                        "collection_path": existdb_client.col_path(col.slug),
                        "query": q,
                        "max_results": "50",
                    },
                )
                root_el = ET.fromstring(raw)
                for hit_el in root_el.findall("hit"):
                    filename = hit_el.get("filename", "")
                    if not filename:
                        continue
                    kwic_el = hit_el.find("kwic")
                    hits.append({
                        "filename": filename,
                        "score": hit_el.get("score", "0"),
                        "kwic": (kwic_el.text or "").strip() if kwic_el is not None else "",
                    })
            except Exception as exc:
                logger.warning(
                    "dynamic_search_failed", slug=website.slug, q=q, error=str(exc)
                )

    theme = website.theme_config or {}
    base = f"/api/v1/sites/{website.slug}"
    visible_pages = [p for p in website.pages if not p.is_hidden]
    hide_header: bool = bool(theme.get("hide_header", False))

    navbar = "" if hide_header else _render_navbar(
        site_title=website.title,
        logo_url=theme.get("logo_url") or None,
        pages=visible_pages,
        nav_config=website.nav_config or [],
        site_base_url=base,
        indices=website.indices,
    )
    footer_note, identifier_url = _footer_parts(
        await db.get(Collection, website.collection_id)
        if website.collection_id else None
    )
    html = _render_page(
        site_title=website.title,
        page_title="Search",
        content=_build_dynamic_search_content(hits, q, base),
        style=_style_block(theme),
        navbar=navbar,
        breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, "Search")]),
        footer_note=footer_note,
        identifier_url=identifier_url,
        meta_tags=_build_meta_tags(website.meta_config or {}),
    )
    if q:
        _set_cached_page(website.slug, path_key, html)
    return html


async def render_dynamic_doc(
    db: AsyncSession, website: Website, filename: str
) -> str:
    """Render a single XML document via XSLT for a DYNAMIC or HYBRID website.

    Results are cached with the website's effective TTL.  The XSLT transform
    is cached separately (invalidated only by metadata changes or clear-cache).
    """
    path_key = f"doc:{filename}"
    ttl = _get_cache_ttl(website)
    cached = _get_cached_page(website.slug, path_key, ttl)
    if cached is not None:
        return cached

    if website.collection_id is None:
        raise NotFoundError("Website has no linked collection.")
    col: Collection | None = await db.get(Collection, website.collection_id)
    if col is None:
        raise NotFoundError("Linked collection not found.")

    xml_bytes = await existdb_client.get_document(col.slug, filename)
    xslt_transform = await _resolve_transform_cached(
        website.slug, website.xslt_config or {}
    )
    doc_body: str = await asyncio.to_thread(xslt_transform, xml_bytes)

    # Try to extract a human-readable label from the doc info list.
    # For dynamic mode we do a quick title-only xquery for the single file; fall back to filename.
    label = filename
    try:
        doc_infos = await _fetch_doc_infos(col)
        for d in doc_infos:
            if d["filename"] == filename:
                label = d.get("title") or filename
                break
    except Exception:
        pass

    theme = website.theme_config or {}
    base = f"/api/v1/sites/{website.slug}"
    visible_pages = [p for p in website.pages if not p.is_hidden]
    hide_header: bool = bool(theme.get("hide_header", False))

    aracne_nav = _parse_aracne_nav(website.nav_config or [])
    browse_hidden = bool(
        next((ap for ap in aracne_nav if ap["id"] == "browse"), {}).get("is_hidden", False)
    )

    navbar = "" if hide_header else _render_navbar(
        site_title=website.title,
        logo_url=theme.get("logo_url") or None,
        pages=visible_pages,
        nav_config=website.nav_config or [],
        site_base_url=base,
        indices=website.indices,
    )
    if browse_hidden:
        crumbs: list[tuple[str | None, str]] = [(f"{base}/", "Home"), (None, label)]
    else:
        crumbs = [(f"{base}/", "Home"), (f"{base}/browse", "Browse"), (None, label)]
    footer_note, identifier_url = _footer_parts(col)
    html = _render_page(
        site_title=website.title,
        page_title=label,
        content=f'<div class="tei-body">{doc_body}</div>',
        style=_style_block(theme),
        navbar=navbar,
        breadcrumb=_render_breadcrumb(crumbs),
        footer_note=footer_note,
        identifier_url=identifier_url,
    )
    _set_cached_page(website.slug, path_key, html)
    return html


async def render_dynamic_page(
    db: AsyncSession, website: Website, page_slug: str
) -> str:
    """Render a free Markdown page for a DYNAMIC website."""
    path_key = f"page:{page_slug}"
    ttl = _get_cache_ttl(website)
    cached = _get_cached_page(website.slug, path_key, ttl)
    if cached is not None:
        return cached

    page = next((p for p in website.pages if p.slug == page_slug), None)
    if page is None or page.is_hidden:
        raise NotFoundError(f"Page '{page_slug}' not found.")

    theme = website.theme_config or {}
    base = f"/api/v1/sites/{website.slug}"
    visible_pages = [p for p in website.pages if not p.is_hidden]
    hide_header: bool = bool(theme.get("hide_header", False))

    navbar = "" if hide_header else _render_navbar(
        site_title=website.title,
        logo_url=theme.get("logo_url") or None,
        pages=visible_pages,
        nav_config=website.nav_config or [],
        site_base_url=base,
        indices=website.indices,
    )
    col: Collection | None = (
        await db.get(Collection, website.collection_id)
        if website.collection_id else None
    )
    footer_note, identifier_url = _footer_parts(col)
    content_html = _md_to_html(page.content_md or "")
    html = _render_page(
        site_title=website.title,
        page_title=page.title,
        content=f"<h1>{_html.escape(page.title)}</h1>\n{content_html}",
        style=_style_block(theme),
        navbar=navbar,
        breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, page.title)]),
        footer_note=footer_note,
        identifier_url=identifier_url,
    )
    _set_cached_page(website.slug, path_key, html)
    return html


def _footer_parts(col: Collection | None) -> tuple[str, str]:
    """Return (footer_note, identifier_url) extracted from *col* metadata."""
    publisher_parts: list[str] = []
    identifier_url = ""
    if col:
        if col.publisher:
            publisher_parts.append(_html.escape(col.publisher))
        if col.pub_year:
            publisher_parts.append(str(col.pub_year))
        if col.identifier_url:
            identifier_url = col.identifier_url
    return ", ".join(publisher_parts), identifier_url


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def _get_website(db: AsyncSession, slug: str) -> Website:
    row = await db.scalar(
        select(Website)
        .where(Website.slug == slug)
        .options(selectinload(Website.pages), selectinload(Website.indices))
    )
    if row is None:
        raise NotFoundError(f"Website '{slug}' not found.")
    return row


async def list_websites(db: AsyncSession) -> list[Website]:
    result = await db.scalars(
        select(Website)
        .options(selectinload(Website.pages), selectinload(Website.indices))
        .order_by(Website.created_at.desc())
    )
    return list(result.all())


async def get_website(db: AsyncSession, slug: str) -> Website:
    return await _get_website(db, slug)


async def create_website(
    db: AsyncSession, data: WebsiteCreate, user_id: uuid.UUID
) -> Website:
    existing = await db.scalar(select(Website).where(Website.slug == data.slug))
    if existing is not None:
        raise ConflictError(f"Website with slug '{data.slug}' already exists.")

    website = Website(
        slug=data.slug,
        title=data.title,
        description=data.description,
        collection_id=data.collection_id,
        rendering_mode=data.rendering_mode,
        theme_config=data.theme_config,
        meta_config=data.meta_config,
        nav_config=data.nav_config,
        xslt_schema_id=data.xslt_schema_id,
        is_published=data.is_published,
        created_by=user_id,
    )
    db.add(website)
    await db.commit()
    # Reload with selectinload(pages) so WebsiteResponse can serialize the
    # relationship without triggering a lazy load (unsupported in async mode).
    return await _get_website(db, website.slug)


async def update_website(
    db: AsyncSession, slug: str, data: WebsiteUpdate
) -> Website:
    website = await _get_website(db, slug)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(website, field, value)
    website.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(website)
    # Any metadata or XSLT change must invalidate the rendered-page and XSLT caches
    # immediately so dynamic/hybrid sites do not serve stale HTML.
    invalidate_cache(slug)
    return website


async def delete_website(db: AsyncSession, slug: str) -> None:
    website = await _get_website(db, slug)
    # Clean up generated static files if they exist.
    site_dir = settings.websites_root / slug
    if site_dir.exists():
        import shutil
        shutil.rmtree(site_dir, ignore_errors=True)
    await db.delete(website)
    await db.commit()


async def get_meta_suggestions(
    db: AsyncSession, slug: str, current_user: User
) -> MetaSuggestionsResponse:
    """Return pre-computed meta field suggestions for the edit form.

    Suggestions are derived from the linked collection's metadata and from
    the users who hold Editor / EditorInChief roles on that collection.
    Intended to pre-populate empty meta_config fields on first edit.
    """
    website = await _get_website(db, slug)

    col: Collection | None = None
    if website.collection_id:
        col = await db.get(Collection, website.collection_id)

    # ── Contributor names (Editor + EiC assigned to the collection) ───────
    contributor_names: list[str] = []
    if col is not None:
        # The directly assigned editor
        if col.editor_id:
            editor = await db.get(User, col.editor_id)
            if editor:
                contributor_names.append(editor.display_name or editor.username)

        # Users with explicit permission grants who carry Editor/EiC role
        result = await db.execute(
            select(User)
            .join(CollectionPermission, CollectionPermission.user_id == User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                CollectionPermission.collection_id == col.id,
                Role.name.in_([RoleName.Editor, RoleName.EditorInChief]),
                UserRole.revoked_at.is_(None),
            )
            .distinct()
        )
        for u in result.scalars().all():
            name = u.display_name or u.username
            if name not in contributor_names:
                contributor_names.append(name)

    # ── Designer is the currently logged-in user ──────────────────────────
    designer_name = current_user.display_name or current_user.username

    # ── Publisher / copyright come from the collection's TEI metadata ─────
    publisher: str = col.publisher if col and col.publisher else ""

    # ── Identifier: use the collection's persistent identifier URL ────────
    identifier: str = col.identifier_url if col and col.identifier_url else ""

    return MetaSuggestionsResponse(
        author=contributor_names,
        dc_creator=contributor_names,
        designer=[designer_name],
        copyright=publisher,
        dc_publisher=[publisher] if publisher else [],
        dc_format="text/html",
        dc_identifier=identifier,
    )


# ── Pages ─────────────────────────────────────────────────────────────────────

async def create_website_page(
    db: AsyncSession, website_id: uuid.UUID, data: WebsitePageCreate
) -> WebsitePage:
    existing = await db.scalar(
        select(WebsitePage).where(
            WebsitePage.website_id == website_id,
            WebsitePage.slug == data.slug,
        )
    )
    if existing is not None:
        raise ConflictError(f"Page with slug '{data.slug}' already exists in this website.")

    page = WebsitePage(
        website_id=website_id,
        slug=data.slug,
        title=data.title,
        content_md=data.content_md,
        sort_order=data.sort_order,
        is_hidden=data.is_hidden,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return page


async def update_website_page(
    db: AsyncSession,
    website_id: uuid.UUID,
    page_slug: str,
    data: WebsitePageUpdate,
) -> WebsitePage:
    page = await db.scalar(
        select(WebsitePage).where(
            WebsitePage.website_id == website_id,
            WebsitePage.slug == page_slug,
        )
    )
    if page is None:
        raise NotFoundError(f"Page '{page_slug}' not found.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(page, field, value)
    page.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(page)
    return page


async def delete_website_page(
    db: AsyncSession, website_id: uuid.UUID, page_slug: str
) -> None:
    page = await db.scalar(
        select(WebsitePage).where(
            WebsitePage.website_id == website_id,
            WebsitePage.slug == page_slug,
        )
    )
    if page is None:
        raise NotFoundError(f"Page '{page_slug}' not found.")
    await db.delete(page)
    await db.commit()


# ── Website indices ───────────────────────────────────────────────────────────

_INDEX_SEP = "|||"


def _parse_index_occurrences(
    raw: bytes,
    key_attr: str | None,
    subkey_attr: str | None,
) -> dict:
    """Parse XQuery index_occurrences.xq output into the cached_data structure.

    Input: newline-separated records, each with 4 fields joined by '|||':
      key ||| subkey ||| text ||| filename

    Output:
    {
      "key_attr": "key",
      "subkey_attr": "role",
      "entries": [{"key": ..., "subentries": [{"subkey": ..., "variants": [...]}]}]
    }
    """
    # Map: key -> subkey -> text -> set[filename]
    tree: dict[str, dict[str, dict[str, set[str]]]] = {}

    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_INDEX_SEP)
        if len(parts) != 4:
            continue
        key_val, subkey_val, text_val, filename = parts
        if not key_val:
            continue

        subkey_map = tree.setdefault(key_val, {})
        text_map = subkey_map.setdefault(subkey_val, {})
        text_map.setdefault(text_val, set()).add(filename)

    entries = []
    for key_val in sorted(tree):
        subentries = []
        for subkey_val in sorted(tree[key_val]):
            variants = []
            for text_val in sorted(tree[key_val][subkey_val]):
                docs = sorted(tree[key_val][subkey_val][text_val])
                variants.append({"text": text_val, "docs": docs})
            subentries.append({"subkey": subkey_val, "variants": variants})
        entries.append({"key": key_val, "subentries": subentries})

    return {
        "key_attr": key_attr or "",
        "subkey_attr": subkey_attr or "",
        "entries": entries,
    }


def _render_index_variant(variant: dict, site_base_url: str) -> str:
    """Render one text variant as an <li> with document reference links."""
    text = variant.get("text", "")
    docs: list[str] = variant.get("docs", [])
    esc_text = _html.escape(text)
    # Append ?highlight=TERM so the target document highlights the term on load.
    hl_param = f"?highlight={_url_quote(text, safe='')}" if text else ""
    refs = " ".join(
        f'<a class="index__ref" href="{_html.escape(f"{site_base_url}/docs/{doc}{hl_param}")}">'
        f'{_html.escape(doc)}</a>'
        for doc in docs
    )
    return (
        f'<li class="index__variant">'
        f'<span class="index__text">{esc_text}</span>'
        f'<span class="index__refs">{refs}</span>'
        f"</li>"
    )


def _build_index_content_parts(index: WebsiteIndex, site_base_url: str) -> list[str]:
    """Return the HTML parts list for a single index's content (entries only).

    Used by both ``render_website_index_html`` (single index page) and
    ``render_all_indices_html`` (aggregated tabbed page).
    """
    cached = index.cached_data or {}
    key_attr = cached.get("key_attr", "")
    subkey_attr = cached.get("subkey_attr", "")
    has_key_attr = bool(key_attr)
    has_subkey_attr = bool(subkey_attr)
    entries: list[dict] = cached.get("entries", [])

    parts: list[str] = [f'<h2 class="index__title">{_html.escape(index.title)}</h2>']
    if not entries:
        parts.append('<p class="index__empty">No entries. Rebuild the index to populate it.</p>')
    else:
        parts.append('<ul class="index__entries">')
        for entry in entries:
            key_val = entry.get("key", "")
            esc_key = _html.escape(key_val)
            parts.append(
                f'<li class="index__entry" data-key="{esc_key}">'
                f'<span class="index__key">{esc_key}</span>'
            )
            subentries: list[dict] = entry.get("subentries", [])

            if has_key_attr:
                # Grouped by key attribute → show subkey and text-variant levels.
                parts.append('<ul class="index__subentries">')
                for subentry in subentries:
                    subkey_val = subentry.get("subkey", "")
                    variants: list[dict] = subentry.get("variants", [])
                    if has_subkey_attr and subkey_val:
                        esc_subkey = _html.escape(subkey_val)
                        parts.append(
                            f'<li class="index__subentry" data-subkey="{esc_subkey}">'
                            f'<span class="index__subkey">{esc_subkey}</span>'
                            '<ul class="index__variants">'
                        )
                        for variant in variants:
                            parts.append(_render_index_variant(variant, site_base_url))
                        parts.append("</ul></li>")
                    else:
                        # No subkey grouping: render variants directly inside the entry.
                        parts.append('<ul class="index__variants">')
                        for variant in variants:
                            parts.append(_render_index_variant(variant, site_base_url))
                        parts.append("</ul>")
                parts.append("</ul>")
            else:
                # No key attribute: key = text content, no variant level.
                # subentries may still have a subkey (e.g. role).
                if has_subkey_attr and subentries:
                    parts.append('<ul class="index__subentries">')
                    for subentry in subentries:
                        subkey_val = subentry.get("subkey", "")
                        esc_subkey = _html.escape(subkey_val)
                        all_docs: list[str] = []
                        for v in subentry.get("variants", []):
                            all_docs.extend(v.get("docs", []))
                        all_docs = sorted(set(all_docs))
                        # key_val is the text that appears in the document.
                        hl_param = f"?highlight={_url_quote(key_val, safe='')}" if key_val else ""
                        refs = " ".join(
                            f'<a class="index__ref" href="{_html.escape(f"{site_base_url}/docs/{doc}{hl_param}")}">'
                            f'{_html.escape(doc)}</a>'
                            for doc in all_docs
                        )
                        parts.append(
                            f'<li class="index__subentry" data-subkey="{esc_subkey}">'
                            f'<span class="index__subkey">{esc_subkey}</span>'
                            f'<span class="index__refs">{refs}</span></li>'
                        )
                    parts.append("</ul>")
                else:
                    # No key, no subkey: just list the documents.
                    all_docs_flat: list[str] = []
                    for subentry in subentries:
                        for v in subentry.get("variants", []):
                            all_docs_flat.extend(v.get("docs", []))
                    all_docs_flat = sorted(set(all_docs_flat))
                    hl_param = f"?highlight={_url_quote(key_val, safe='')}" if key_val else ""
                    refs = " ".join(
                        f'<a class="index__ref" href="{_html.escape(f"{site_base_url}/docs/{doc}{hl_param}")}">'
                        f'{_html.escape(doc)}</a>'
                        for doc in all_docs_flat
                    )
                    parts.append(f'<span class="index__refs">{refs}</span>')

            parts.append("</li>")
        parts.append("</ul>")

    return parts


def render_website_index_html(website: Website, index: WebsiteIndex) -> str:
    """Generate the HTML page for a website index from its cached_data.

    The cached_data is produced by rebuild_website_index() which runs the
    index_occurrences XQuery and aggregates results into a JSON structure.
    """
    theme = website.theme_config or {}
    style = _style_block(theme)
    site_base_url = f"/api/v1/sites/{website.slug}"

    navbar = _render_navbar(
        site_title=website.title,
        logo_url=theme.get("logo_url") or None,
        pages=[p for p in website.pages if not p.is_hidden],
        nav_config=website.nav_config or [],
        site_base_url=site_base_url,
        indices=website.indices,
    )
    breadcrumb = _render_breadcrumb(
        [(f"{site_base_url}/", website.title), (None, index.title)]
    )

    esc_title = _html.escape(index.title)
    filter_input = (
        f'<input class="index__filter" type="search" placeholder="Filter {esc_title}…"'
        f' aria-label="Filter {esc_title}">'
        '<p class="index__filter-empty">No results.</p>'
    )
    filter_script = (
        "<script>"
        "(function(){"
        "var inp=document.querySelector('.index__filter');"
        "if(!inp)return;"
        "inp.addEventListener('input',function(){"
        "var val=inp.value.trim().toLowerCase();"
        "var entries=document.querySelectorAll('.index__entry');"
        "var vis=0;"
        "entries.forEach(function(e){"
        "var show=!val||e.textContent.toLowerCase().indexOf(val)!==-1;"
        "e.style.display=show?'':'none';"
        "if(show)vis++;"
        "});"
        "var em=document.querySelector('.index__filter-empty');"
        "if(em)em.style.display=(vis===0&&entries.length>0)?'':'none';"
        "});})();"
        "</script>"
    )
    parts = _build_index_content_parts(index, site_base_url)
    content = "<main>" + filter_input + "".join(parts) + "</main>" + filter_script
    return _render_page(
        site_title=website.title,
        page_title=index.title,
        content=content,
        style=style,
        navbar=navbar,
        breadcrumb=breadcrumb,
        meta_tags=_build_meta_tags(website.meta_config or {}),
    )


def render_all_indices_html(
    website: Website,
    *,
    site_base_url: str = "",
    path_prefix: str = "",
) -> str:
    """Generate a tabbed HTML page aggregating all built indices.

    Only indices whose ``cached_data`` is not None are included.
    ``site_base_url`` is used for dynamic/hybrid rendering (e.g.
    ``/api/v1/sites/my-site``).  For static builds, leave it empty and set
    ``path_prefix`` to the relative path from the current page to the site root
    (empty string for root-level pages, ``../`` for subdirectory pages).
    """
    built = [idx for idx in (website.indices or []) if idx.cached_data is not None]

    theme = website.theme_config or {}
    style = _style_block(theme)

    effective_base = site_base_url or f"/api/v1/sites/{website.slug}"

    navbar = _render_navbar(
        site_title=website.title,
        logo_url=theme.get("logo_url") or None,
        pages=[p for p in website.pages if not p.is_hidden],
        nav_config=website.nav_config or [],
        site_base_url=site_base_url,
        path_prefix=path_prefix,
        indices=website.indices,
    )
    home_link = f"{site_base_url}/" if site_base_url else f"{path_prefix}index.html"
    breadcrumb = _render_breadcrumb([(home_link, website.title), (None, "Indices")])

    if not built:
        content = "<main><p>No indices built yet.</p></main>"
        return _render_page(
            site_title=website.title,
            page_title="Indices",
            content=content,
            style=style,
            navbar=navbar,
            breadcrumb=breadcrumb,
            meta_tags=_build_meta_tags(website.meta_config or {}),
        )

    # Tab buttons
    btn_parts: list[str] = ['<div class="indices-tabs-btns">']
    for i, idx in enumerate(built):
        active_cls = " active" if i == 0 else ""
        btn_parts.append(
            f'<button class="indices-tab-btn{active_cls}" data-tab="{i}">'
            f'{_html.escape(idx.title)}</button>'
        )
    btn_parts.append("</div>")

    # Tab panels — each with a filter input at the top
    panel_parts: list[str] = ['<div class="indices-tab-panels">']
    for i, idx in enumerate(built):
        active_cls = " active" if i == 0 else ""
        esc_label = _html.escape(idx.title)
        panel_parts.append(f'<div class="indices-panel{active_cls}" data-panel="{i}">')
        panel_parts.append(
            f'<input class="index__filter" type="search" placeholder="Filter {esc_label}…"'
            f' aria-label="Filter {esc_label}">'
        )
        panel_parts.append('<p class="index__filter-empty">No results.</p>')
        panel_parts.extend(_build_index_content_parts(idx, effective_base))
        panel_parts.append("</div>")
    panel_parts.append("</div>")

    tab_script = (
        "<script>"
        # Tab switching — also clears the filter and resets entry visibility
        "var _ibtns=document.querySelectorAll('.indices-tab-btn');"
        "var _ipanels=document.querySelectorAll('.indices-panel');"
        "function _clearFilter(panel){"
        "var f=panel.querySelector('.index__filter');if(f)f.value='';"
        "panel.querySelectorAll('.index__entry').forEach(function(e){e.style.display='';});"
        "var em=panel.querySelector('.index__filter-empty');if(em)em.style.display='none';"
        "}"
        "_ibtns.forEach(function(b,i){"
        "b.addEventListener('click',function(){"
        "_ibtns.forEach(function(x){x.classList.remove('active');});"
        "_ipanels.forEach(function(p){p.classList.remove('active');_clearFilter(p);});"
        "b.classList.add('active');_ipanels[i].classList.add('active');"
        "});});"
        # Filter logic — scoped to the parent panel
        "document.querySelectorAll('.index__filter').forEach(function(inp){"
        "inp.addEventListener('input',function(){"
        "var val=inp.value.trim().toLowerCase();"
        "var panel=inp.closest('.indices-panel');"
        "var entries=panel.querySelectorAll('.index__entry');"
        "var vis=0;"
        "entries.forEach(function(e){"
        "var show=!val||e.textContent.toLowerCase().indexOf(val)!==-1;"
        "e.style.display=show?'':'none';"
        "if(show)vis++;"
        "});"
        "var em=panel.querySelector('.index__filter-empty');"
        "if(em)em.style.display=(vis===0&&entries.length>0)?'':'none';"
        "});});"
        "</script>"
    )

    content_parts = [
        '<main>',
        '<h1 class="indices-page-title">Indices</h1>',
        '<div class="indices-tabs">',
        *btn_parts,
        *panel_parts,
        '</div>',
        '</main>',
        tab_script,
    ]

    return _render_page(
        site_title=website.title,
        page_title="Indices",
        content="".join(content_parts),
        style=style,
        navbar=navbar,
        breadcrumb=breadcrumb,
        meta_tags=_build_meta_tags(website.meta_config or {}),
    )


async def list_website_indices(db: AsyncSession, website_id: uuid.UUID) -> list[WebsiteIndex]:
    result = await db.scalars(
        select(WebsiteIndex)
        .where(WebsiteIndex.website_id == website_id)
        .order_by(WebsiteIndex.created_at)
    )
    return list(result.all())


async def get_website_index(
    db: AsyncSession, website_id: uuid.UUID, index_id: uuid.UUID
) -> WebsiteIndex:
    idx = await db.scalar(
        select(WebsiteIndex).where(
            WebsiteIndex.id == index_id,
            WebsiteIndex.website_id == website_id,
        )
    )
    if idx is None:
        raise NotFoundError(f"Index '{index_id}' not found.")
    return idx


async def create_website_index(
    db: AsyncSession, website_id: uuid.UUID, data: WebsiteIndexCreate
) -> WebsiteIndex:
    existing = await db.scalar(
        select(WebsiteIndex).where(
            WebsiteIndex.website_id == website_id,
            WebsiteIndex.label == data.label,
        )
    )
    if existing is not None:
        raise ConflictError(f"Index with label '{data.label}' already exists in this website.")
    idx = WebsiteIndex(
        website_id=website_id,
        label=data.label,
        title=data.title,
        tag=data.tag,
        key_attribute=data.key_attribute,
        subkey_attribute=data.subkey_attribute,
    )
    db.add(idx)
    await db.commit()
    await db.refresh(idx)
    return idx


async def update_website_index(
    db: AsyncSession,
    website_id: uuid.UUID,
    index_id: uuid.UUID,
    data: WebsiteIndexUpdate,
) -> WebsiteIndex:
    idx = await get_website_index(db, website_id, index_id)
    # Check label uniqueness when changing it.
    if data.label is not None and data.label != idx.label:
        clash = await db.scalar(
            select(WebsiteIndex).where(
                WebsiteIndex.website_id == website_id,
                WebsiteIndex.label == data.label,
            )
        )
        if clash is not None:
            raise ConflictError(f"Index with label '{data.label}' already exists.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(idx, field, value)
    idx.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(idx)
    return idx


async def delete_website_index(
    db: AsyncSession, website_id: uuid.UUID, index_id: uuid.UUID
) -> None:
    idx = await get_website_index(db, website_id, index_id)
    await db.delete(idx)
    await db.commit()


async def rebuild_website_index(
    db: AsyncSession, slug: str, index_id: uuid.UUID
) -> WebsiteIndex:
    """Run the index_occurrences XQuery and update the index cached_data.

    Raises NotFoundError if the website has no linked collection.
    """
    website = await _get_website(db, slug)
    if website.collection_id is None:
        raise NotFoundError("Website has no linked collection — cannot build index.")
    col: Collection | None = await db.get(Collection, website.collection_id)
    if col is None:
        raise NotFoundError("Linked collection not found.")

    idx = await get_website_index(db, website.id, index_id)
    path = existdb_client.col_path(col.slug)
    raw = await existdb_client.xquery(
        "collections/index_occurrences.xq",
        {
            "path": path,
            "tag": idx.tag,
            "key_attr": idx.key_attribute or "",
            "subkey_attr": idx.subkey_attribute or "",
        },
    )
    idx.cached_data = _parse_index_occurrences(raw, idx.key_attribute, idx.subkey_attribute)
    idx.last_built_at = datetime.now(UTC)
    idx.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(idx)
    # Invalidate page cache so the navbar (which shows built indices) refreshes.
    invalidate_cache(slug)
    return idx


async def rebuild_all_website_indices(db: AsyncSession, slug: str) -> list[WebsiteIndex]:
    """Rebuild every index configured on the website.  Returns rebuilt indices."""
    website = await _get_website(db, slug)
    if website.collection_id is None:
        raise NotFoundError("Website has no linked collection — cannot build indices.")
    col: Collection | None = await db.get(Collection, website.collection_id)
    if col is None:
        raise NotFoundError("Linked collection not found.")
    path = existdb_client.col_path(col.slug)

    rebuilt: list[WebsiteIndex] = []
    for idx in website.indices:
        raw = await existdb_client.xquery(
            "collections/index_occurrences.xq",
            {
                "path": path,
                "tag": idx.tag,
                "key_attr": idx.key_attribute or "",
                "subkey_attr": idx.subkey_attribute or "",
            },
        )
        idx.cached_data = _parse_index_occurrences(raw, idx.key_attribute, idx.subkey_attribute)
        idx.last_built_at = datetime.now(UTC)
        idx.updated_at = datetime.now(UTC)
        rebuilt.append(idx)

    if rebuilt:
        await db.commit()
        for idx in rebuilt:
            await db.refresh(idx)
        invalidate_cache(slug)
    return rebuilt


async def refresh_website_tags(db: AsyncSession, slug: str) -> Website:
    """Run distinct_tags XQuery against the linked collection and cache the result.

    The cached dict maps element local-names to lists of attribute local-names:
      {"persName": ["key", "role"], "placeName": ["ref"]}
    """
    website = await _get_website(db, slug)
    if website.collection_id is None:
        raise NotFoundError("Website has no linked collection — cannot refresh tags.")
    col: Collection | None = await db.get(Collection, website.collection_id)
    if col is None:
        raise NotFoundError("Linked collection not found.")

    path = existdb_client.col_path(col.slug)
    raw = await existdb_client.xquery("collections/distinct_tags.xq", {"path": path})
    website.distinct_tags = json.loads(raw.decode("utf-8"))
    website.tags_refreshed_at = datetime.now(UTC)
    website.updated_at = datetime.now(UTC)
    await db.commit()
    return await _get_website(db, slug)


# ── Static build (Option A) ───────────────────────────────────────────────────

async def trigger_build(db: AsyncSession, slug: str) -> None:
    """Mark the website as pending — the caller schedules _run_build as background task."""
    website = await _get_website(db, slug)
    website.build_status = BuildStatus.pending
    website.build_error = None
    website.updated_at = datetime.now(UTC)
    await db.commit()


async def run_build(slug: str) -> None:
    """Background task: generate the site for *slug*.

    Creates its own AsyncSession so it can run after the HTTP response is sent.

    - STATIC  → full build: index, browse, docs, pages, search + search.json
    - HYBRID  → structural build: index, browse, pages only (docs always dynamic)
    - DYNAMIC → no-op: nothing to build, mark done immediately
    """
    async with AsyncSessionLocal() as db:
        try:
            website = await _get_website(db, slug)

            if website.rendering_mode == RenderingMode.DYNAMIC:
                website.build_status = BuildStatus.done
                website.last_build_at = datetime.now(UTC)
                await db.commit()
                return

            website.build_status = BuildStatus.building
            website.updated_at = datetime.now(UTC)
            await db.commit()

            if website.rendering_mode == RenderingMode.HYBRID:
                await _build_hybrid_site(db, website)
            else:  # STATIC
                await _build_static_site(db, website)

            website.build_status = BuildStatus.done
            website.build_error = None
            website.last_build_at = datetime.now(UTC)
            website.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info("website_build_done", slug=slug, mode=website.rendering_mode.value)

        except Exception as exc:
            logger.error("website_build_failed", slug=slug, error=str(exc))
            try:
                async with AsyncSessionLocal() as err_db:
                    w = await err_db.scalar(select(Website).where(Website.slug == slug))
                    if w:
                        w.build_status = BuildStatus.failed
                        w.build_error = str(exc)
                        w.updated_at = datetime.now(UTC)
                        await err_db.commit()
            except Exception:
                pass


async def _build_static_site(db: AsyncSession, website: Website) -> None:
    """Generate all HTML files for *website* into settings.websites_root / slug /.

    Output structure:
      index.html      — cover/hero page with CTA → browse.html
      browse.html     — document list
      docs/{f}.html   — per-document rendered HTML (via XSLT)
      pages/{s}.html  — free Markdown pages
      search.json.gz  — gzip-compressed full-text index (title, author, body) for client-side search
    """
    import defusedxml.ElementTree as ET

    slug = website.slug
    theme = website.theme_config or {}
    logo_url: str | None = theme.get("logo_url") or None

    site_dir = settings.websites_root / slug
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "docs").mkdir(exist_ok=True)
    (site_dir / "pages").mkdir(exist_ok=True)

    style = _style_block(theme)

    # Only visible free pages appear in the navigation.
    visible_pages = [p for p in website.pages if not p.is_hidden]

    # Resolve Aracne system-page visibility from nav_config.
    aracne_nav = _parse_aracne_nav(website.nav_config or [])
    _nav_map = {ap["id"]: ap for ap in aracne_nav}
    browse_hidden: bool = bool(_nav_map.get("browse", {}).get("is_hidden", False))
    search_hidden: bool = bool(_nav_map.get("search", {}).get("is_hidden", False))
    indices_hidden: bool = bool(_nav_map.get("indices", {}).get("is_hidden", False))

    # When hide_header is set, every page is rendered without a navbar.
    hide_header: bool = bool(theme.get("hide_header", False))

    # Navbars for root-level pages and subdirectory pages differ only in prefix.
    def navbar(path_prefix: str = "") -> str:
        if hide_header:
            return ""
        return _render_navbar(
            site_title=website.title,
            logo_url=logo_url,
            pages=visible_pages,
            path_prefix=path_prefix,
            nav_config=website.nav_config or [],
            indices=website.indices,
        )

    # Resolve the XSLT transform once for the whole build.
    xslt_transform = await _resolve_transform(website.xslt_config or {})

    # ── Fetch collection metadata and document list ────────────────────────
    doc_infos: list[dict] = []
    col: Collection | None = None

    if website.collection_id is not None:
        col = await db.get(Collection, website.collection_id)

    if col is not None:
        col_path = existdb_client.col_path(col.slug)
        try:
            raw = await existdb_client.xquery(
                "collections/list_with_titles.xq",
                variables={"collection_path": col_path},
            )
            root_el = ET.fromstring(raw)
            for el in root_el.findall("doc"):
                filename = (el.findtext("filename") or "").strip()
                if not filename:
                    continue
                doc_infos.append(
                    {
                        "filename": filename,
                        "title": (el.findtext("title") or "").strip() or None,
                        "author": (el.findtext("author") or "").strip() or None,
                    }
                )
        except Exception as exc:
            logger.warning("website_build_list_docs_failed", slug=slug, error=str(exc))
            try:
                filenames = await existdb_client.list_collection(col.slug)
                doc_infos = [{"filename": f, "title": None, "author": None} for f in filenames]
            except Exception:
                doc_infos = []

    # Build meta tags string (same on every page of this site).
    meta_tags: str = _build_meta_tags(website.meta_config or {})

    # Build publisher / year string and identifier URL for every page footer.
    publisher_parts: list[str] = []
    identifier_url: str = ""
    if col:
        if col.publisher:
            publisher_parts.append(_html.escape(col.publisher))
        if col.pub_year:
            publisher_parts.append(str(col.pub_year))
        if col.identifier_url:
            identifier_url = col.identifier_url
    footer_note = ", ".join(publisher_parts)

    # ── index.html — cover / hero page ────────────────────────────────────
    index_html = _render_page(
        site_title=website.title,
        page_title=website.title,
        content=_build_cover_content(
            website_title=website.title,
            col=col,
            doc_count=len(doc_infos),
            theme=theme,
            pages=visible_pages,
            nav_config=website.nav_config or [],
            indices=website.indices,
        ),
        style=style,
        navbar=navbar(),
        footer_note=footer_note,
        identifier_url=identifier_url,
        meta_tags=meta_tags,
    )
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")

    # ── browse.html — document list (skipped when hidden) ─────────────────
    if not browse_hidden:
        browse_html = _render_page(
            site_title=website.title,
            page_title="Browse",
            content=_build_browse_content(doc_infos),
            style=style,
            navbar=navbar(),
            breadcrumb=_render_breadcrumb([("index.html", "Home"), (None, "Browse")]),
            footer_note=footer_note,
            identifier_url=identifier_url,
            meta_tags=meta_tags,
        )
        (site_dir / "browse.html").write_text(browse_html, encoding="utf-8")

    # ── docs/{filename}.html — individual documents ────────────────────────
    # doc_bodies accumulates plain text for the full-text search index.
    doc_bodies: dict[str, str] = {}

    if col is not None:
        for doc_info in doc_infos:
            filename = doc_info["filename"]
            try:
                xml_bytes = await existdb_client.get_document(col.slug, filename)
                doc_body = await asyncio.to_thread(xslt_transform, xml_bytes)
                doc_bodies[filename] = _extract_plain_text(xml_bytes)
            except Exception as exc:
                logger.warning(
                    "website_build_doc_failed", slug=slug, filename=filename, error=str(exc)
                )
                doc_body = f"<p>Could not render document: {_html.escape(str(exc))}</p>"

            label = doc_info.get("title") or filename
            if browse_hidden:
                doc_crumbs: list[tuple[str | None, str]] = [
                    ("../index.html", "Home"),
                    (None, label),
                ]
            else:
                doc_crumbs = [
                    ("../index.html", "Home"),
                    ("../browse.html", "Browse"),
                    (None, label),
                ]
            doc_html = _render_page(
                site_title=website.title,
                page_title=label,
                content=f'<div class="tei-body">{doc_body}</div>',
                style=style,
                navbar=navbar("../"),
                breadcrumb=_render_breadcrumb(doc_crumbs),
                footer_note=footer_note,
                identifier_url=identifier_url,
            )
            (site_dir / "docs" / f"{filename}.html").write_text(doc_html, encoding="utf-8")

    # ── pages/{slug}.html — free Markdown pages (hidden pages are skipped) ──
    for page in visible_pages:
        content_html = _md_to_html(page.content_md or "")
        page_html = _render_page(
            site_title=website.title,
            page_title=page.title,
            content=f"<h1>{_html.escape(page.title)}</h1>\n{content_html}",
            style=style,
            navbar=navbar("../"),
            breadcrumb=_render_breadcrumb([("../index.html", "Home"), (None, page.title)]),
            footer_note=footer_note,
            identifier_url=identifier_url,
        )
        (site_dir / "pages" / f"{page.slug}.html").write_text(page_html, encoding="utf-8")

    # ── search.html — client-side search page (skipped when hidden) ──────
    if not search_hidden:
        search_html = _render_page(
            site_title=website.title,
            page_title="Search",
            content=_build_search_content(),
            style=style,
            navbar=navbar(),
            breadcrumb=_render_breadcrumb([("index.html", "Home"), (None, "Search")]),
            footer_note=footer_note,
            identifier_url=identifier_url,
            meta_tags=meta_tags,
        )
        (site_dir / "search.html").write_text(search_html, encoding="utf-8")

    # ── search.json.gz — gzip-compressed full-text index ─────────────────────
    # Each entry includes the plain-text body of the document so that the
    # browser-side search can match against the full content, not just metadata.
    # The file is gzip-compressed (typically 70-80 % smaller than plain JSON)
    # and decompressed natively by the browser via the DecompressionStream API.
    search_index = [
        {
            "filename": d["filename"],
            "title": d.get("title") or d["filename"],
            "author": d.get("author") or "",
            "url": f"docs/{d['filename']}.html",
            "body": doc_bodies.get(d["filename"], ""),
        }
        for d in doc_infos
    ]
    json_bytes = json.dumps(
        search_index, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    (site_dir / "search.json.gz").write_bytes(gzip.compress(json_bytes, compresslevel=9))

    # ── indices.html — aggregated indices page (skipped when hidden or empty) ─
    built_indices = [idx for idx in (website.indices or []) if idx.cached_data is not None]
    if not indices_hidden and built_indices:
        indices_html = render_all_indices_html(website)
        (site_dir / "indices.html").write_text(indices_html, encoding="utf-8")


async def _build_hybrid_site(db: AsyncSession, website: Website) -> None:
    """Build the structural pages for a HYBRID website.

    Structural pages written to disk (served via FileResponse):
      index.html     — cover / hero page
      browse.html    — document list (links to dynamic doc endpoint)
      pages/{s}.html — free Markdown pages

    Not built (served dynamically at request time):
      docs/{filename}  — always rendered live from eXist-db
      search           — server-side FT search via render_dynamic_search()

    All hrefs inside the built pages use absolute paths rooted at
    ``/api/v1/sites/{slug}/`` so that navbar and content links resolve
    correctly regardless of which static file is being served.
    """
    slug = website.slug
    theme = website.theme_config or {}
    logo_url: str | None = theme.get("logo_url") or None
    base = f"/api/v1/sites/{slug}"

    site_dir = settings.websites_root / slug
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "pages").mkdir(exist_ok=True)

    style = _style_block(theme)
    visible_pages = [p for p in website.pages if not p.is_hidden]

    aracne_nav = _parse_aracne_nav(website.nav_config or [])
    _nav_map = {ap["id"]: ap for ap in aracne_nav}
    browse_hidden: bool = bool(_nav_map.get("browse", {}).get("is_hidden", False))
    indices_hidden: bool = bool(_nav_map.get("indices", {}).get("is_hidden", False))
    hide_header: bool = bool(theme.get("hide_header", False))

    def _navbar() -> str:
        if hide_header:
            return ""
        return _render_navbar(
            site_title=website.title,
            logo_url=logo_url,
            pages=visible_pages,
            nav_config=website.nav_config or [],
            site_base_url=base,
            indices=website.indices,
        )

    # Fetch doc list for cover doc-count and browse page.
    col: Collection | None = (
        await db.get(Collection, website.collection_id)
        if website.collection_id is not None else None
    )
    doc_infos: list[dict] = await _fetch_doc_infos(col) if col is not None else []

    meta_tags: str = _build_meta_tags(website.meta_config or {})
    footer_note, identifier_url = _footer_parts(col)

    # ── index.html ────────────────────────────────────────────────────────
    index_html = _render_page(
        site_title=website.title,
        page_title=website.title,
        content=_build_cover_content(
            website_title=website.title,
            col=col,
            doc_count=len(doc_infos),
            theme=theme,
            pages=visible_pages,
            nav_config=website.nav_config or [],
            site_base_url=base,
            indices=website.indices,
        ),
        style=style,
        navbar=_navbar(),
        footer_note=footer_note,
        identifier_url=identifier_url,
        meta_tags=meta_tags,
    )
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")

    # ── browse.html — document list (skipped when hidden) ─────────────────
    if not browse_hidden:
        browse_html = _render_page(
            site_title=website.title,
            page_title="Browse",
            content=_build_browse_content(doc_infos, site_base_url=base),
            style=style,
            navbar=_navbar(),
            breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, "Browse")]),
            footer_note=footer_note,
            identifier_url=identifier_url,
            meta_tags=meta_tags,
        )
        (site_dir / "browse.html").write_text(browse_html, encoding="utf-8")

    # ── pages/{slug}.html — free Markdown pages ───────────────────────────
    for page in visible_pages:
        content_html = _md_to_html(page.content_md or "")
        page_html = _render_page(
            site_title=website.title,
            page_title=page.title,
            content=f"<h1>{_html.escape(page.title)}</h1>\n{content_html}",
            style=style,
            navbar=_navbar(),
            breadcrumb=_render_breadcrumb(
                [(f"{base}/", "Home"), (None, page.title)]
            ),
            footer_note=footer_note,
            identifier_url=identifier_url,
        )
        (site_dir / "pages" / f"{page.slug}.html").write_text(
            page_html, encoding="utf-8"
        )

    # ── indices.html — aggregated indices page (skipped when hidden or empty) ─
    built_indices = [idx for idx in (website.indices or []) if idx.cached_data is not None]
    if not indices_hidden and built_indices:
        indices_page_html = render_all_indices_html(website, site_base_url=base)
        (site_dir / "indices.html").write_text(indices_page_html, encoding="utf-8")

    # After build, invalidate the dynamic render cache so any cached doc pages
    # are refreshed from eXist-db on the next request.
    invalidate_cache(slug)
