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
import shutil
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
from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.core.ssrf import check_ssrf
from app.services.xslt import apply_xslt
from app.db.existdb import existdb_client
from app.db.postgres import AsyncSessionLocal
from app.models.collection import Collection, CollectionStatus
from app.models.collection_permission import CollectionPermission
from app.models.collection_validation_run import (
    CollectionValidationRun,
    ValidationRunStatus,
)
from app.models.role import Role, RoleName, UserRole
from app.models.system_setting import SystemSetting
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
header nav {
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
.hero { padding: 4.5rem 0 3.5rem; text-align: center; position: relative; }
/* Optional background image + coloured overlay. Both are driven by
   CSS custom properties set inline on the .hero element by
   _build_cover_content so the colour, alpha, and image can change
   per-site without regenerating the static CSS. */
.hero.has-bg {
  background-image: var(--hero-bg);
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  color: #fff;
}
.hero.has-bg .lead, .hero.has-bg .meta-block { color: #eef1f5; }
.hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background: var(--hero-overlay, transparent);
  pointer-events: none;
  z-index: 0;
}
.hero > * { position: relative; z-index: 1; }
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
/* Home-page ``fullscreen`` mode — drops the 960px container so the
   hero (and its optional background image) span edge-to-edge. The
   column grid below keeps a comfortable reading width. */
body.home-full main {
  max-width: none;
  margin: 0;
  padding: 0;
}
body.home-full main > .hero { padding-left: 1.5rem; padding-right: 1.5rem; }
body.home-full main > .home-body { max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem; }
/* Home-page ``cover`` mode — the book-cover effect.
   Background image + overlay live on <body> (not on the hero), so
   title, lead, meta, and column grid all stack on top of the same
   bg image. Content flows naturally: the hero is NOT inflated to
   fill the viewport — body text sits right below the title and the
   image stretches to cover whatever vertical space the page needs.
   ``--hero-bg`` / ``--hero-overlay`` are set per-page via an inline
   <style> block emitted by _build_cover_content (see there). */
body.home-cover {
  background-image: var(--hero-bg);
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
  color: #fff;
  /* Sticky-footer flex: body fills at least the viewport; main grows
     to take the leftover space so the footer hugs the bottom of the
     screen on short pages. Longer pages flow naturally — main
     contributes its natural height and the footer sits right after. */
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
}
body.home-cover main { flex: 1 0 auto; }
body.home-cover footer { flex-shrink: 0; }
body.home-cover::before {
  content: "";
  position: fixed;
  inset: 0;
  background: var(--hero-overlay, transparent);
  pointer-events: none;
  z-index: 0;
}
body.home-cover > * { position: relative; z-index: 1; }
body.home-cover main {
  max-width: none;
  margin: 0;
  padding: 0;
  /* No min-height here: ``background-attachment: fixed`` on the body
     keeps the bg image glued to the viewport regardless of how short
     the content is, so the page can fit the screen naturally without
     a padded gap when the title + lead are the only content. */
}
/* Hero in cover mode carries no bg of its own — ``has-bg`` styling
   is overridden so the body image shines through. The per-hero
   ::before overlay is also disabled; the body-level overlay covers
   the whole viewport. */
body.home-cover main > .hero {
  padding: 4.5rem 1.5rem 2rem;
  min-height: 0;
  background: none;
  color: #fff;
}
body.home-cover main > .hero::before { display: none; }
body.home-cover main > .hero h1 { color: #fff; }
body.home-cover main > .hero .lead { color: #eef1f5; }
body.home-cover main > .hero .meta-block { color: #d1d5db; }
body.home-cover main > .home-body {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 1.5rem 3rem;
}
/* Text on top of the bg needs light-on-dark defaults. */
body.home-cover .home-col,
body.home-cover .home-col p,
body.home-cover .home-col li { color: #f1f5f9; }
body.home-cover .home-col h2,
body.home-cover .home-col h3,
body.home-cover .home-col h4 { color: #fff; }
body.home-cover .home-col a { color: #fde68a; }
body.home-cover footer { background: rgba(0, 0, 0, 0.45); color: rgba(255, 255, 255, 0.85); }
body.home-cover footer a { color: #fde68a; }
h1 { font-size: 1.8rem; margin-bottom: 0.5rem; line-height: 1.2; }
h2 { font-size: 1.25rem; margin: 2rem 0 0.75rem; }
h3 { font-size: 1.05rem; margin: 1.5rem 0 0.5rem; }
p { margin-bottom: 1rem; }
a { color: var(--primary); }
ul { margin: 0.5rem 0 1rem 1.5rem; }
li { margin-bottom: 0.3rem; }
.doc-count { font-size: 0.85rem; color: #6b7280; margin-bottom: 1rem; }
.browse-filter { display:block; width:100%; max-width:30rem; padding:.45rem .75rem;
  font-size:.9rem; border:1px solid #d1d5db; border-radius:4px; margin-bottom:1.25rem;
  outline:none; box-sizing:border-box; }
.browse-filter:focus { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(99,102,241,.15); }
.browse-no-results { font-size:.9rem; color:#9ca3af; padding:1rem 0; }
.doc-list { list-style: none; margin-left: 0; }
.doc-list li { border-bottom: 1px solid #e5e7eb; padding: 0.75rem 0; }
.doc-list a { font-weight: 500; }
.doc-list .doc-title { font-weight: 500; }
.doc-meta { font-size: 0.85rem; color: #6b7280; margin-top: 0.2rem; }
.doc-meta .doc-author { display: inline; }
.doc-meta .doc-filename { display: inline; font-family: monospace; font-size: 0.8rem;
  color: #9ca3af; margin-left: 0.5rem; }
.browse-toolbar { display:flex; align-items:center; flex-wrap:wrap;
  gap:.5rem; margin-bottom:1rem; }
.browse-sort-label { font-size:.8rem; color:#6b7280; white-space:nowrap; }
.browse-sort-btn { padding:.25rem .6rem; font-size:.8rem; border:1px solid #d1d5db;
  border-radius:3px; background:#fff; cursor:pointer; display:inline-flex;
  align-items:center; gap:.25rem; }
.browse-sort-btn:hover { background:#f3f4f6; }
.browse-sort-btn.sort-active { border-color:var(--primary); color:var(--primary);
  font-weight:600; }
.browse-sort-btn .sort-arrow { font-size:.7rem; }
.browse-pagination { display:flex; align-items:center; gap:.35rem;
  flex-wrap:wrap; margin-top:1.5rem; }
.browse-pagination button { padding:.3rem .65rem; font-size:.82rem; border:1px solid #d1d5db;
  border-radius:3px; background:#fff; cursor:pointer; line-height:1.4; }
.browse-pagination button:hover:not(:disabled) { background:#f3f4f6; }
.browse-pagination button.active { background:var(--primary); color:#fff;
  border-color:var(--primary); font-weight:600; }
.browse-pagination button:disabled { opacity:.4; cursor:default; }
.browse-pagination .pg-ellipsis { padding:.3rem .3rem; font-size:.82rem; color:#9ca3af; }
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
/* ── Document action bar (Scarica TEI / Scarica PDF) ──────────────── */
.doc-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0 0 1.25rem; }
.doc-action  {
  display: inline-flex; align-items: center; gap: 0.35rem;
  padding: 0.35rem 0.85rem; border-radius: 0.375rem;
  font-size: 0.82rem; font-family: var(--font); cursor: pointer;
  border: 1px solid #d1d5db; background: #fff; color: #374151;
  text-decoration: none;
}
.doc-action:hover { background: #f3f4f6; color: #1f2937; }
@media print { .doc-actions { display: none !important; } }
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
/* TEI valid badge — shield + label rendered in the footer when the
   collection's latest full-collection validation run is green. The
   ``#tei-valid-badge`` id is deliberately stable so deployments can
   hide or restyle the badge via their site's custom CSS without a
   core change. */
#tei-valid-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: #d1fae5;
  color: #065f46;
  text-decoration: none;
  font-weight: 500;
  font-size: 0.75rem;
  line-height: 1.1;
  vertical-align: baseline;
}
#tei-valid-badge:hover { opacity: 0.9; text-decoration: none; }
#tei-valid-badge svg { width: 0.85rem; height: 0.85rem; }
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
/* Separator when two column-widget navs are placed consecutively */
.col-page-menu + .col-index-list,
.col-index-list + .col-page-menu,
.col-search-widget + .col-page-menu,
.col-search-widget + .col-index-list,
.col-page-menu + .col-search-widget,
.col-index-list + .col-search-widget {
  margin-top: 1.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid #e5e7eb;
}
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
.search-box { display: flex; gap: 0.5rem; align-items: center; }
.search-box input[type=search] {
  flex: 1;
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
.search-submit {
  padding: 0.625rem 1.25rem;
  font-size: 1rem;
  font-family: inherit;
  font-weight: 600;
  color: #fff;
  background: var(--primary);
  border: none;
  border-radius: 0.5rem;
  cursor: pointer;
  white-space: nowrap;
}
.search-submit:hover { opacity: 0.88; }
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
/* ── Entity hover preview tooltip ───────────────────────────────────
   Floating popover for the opt-in Wikidata hover feature. Created
   and positioned at runtime by the JS in _build_entity_hover_js
   when ``xslt_config.entity_hover.enabled`` is true on the site.
   The styles are unconditional — they only take effect once a
   ``.tei-entity-hover-tip`` element is actually inserted. */
.tei-entity-hover-tip {
  position: absolute;
  z-index: 1000;
  max-width: 280px;
  background: #1e293b;
  color: #f8fafc;
  padding: .5rem .7rem;
  border-radius: 6px;
  box-shadow: 0 4px 18px rgba(0, 0, 0, .35);
  font-size: .82rem;
  line-height: 1.4;
  pointer-events: none;
}
.tei-entity-hover-tip img.tei-entity-hover-img {
  display: block;
  max-width: 100%;
  max-height: 140px;
  object-fit: contain;
  border-radius: 3px;
  margin-bottom: .4rem;
  background: rgba(255, 255, 255, 0.04);
}
.tei-entity-hover-tip .tei-entity-hover-label {
  font-weight: 600;
  margin-bottom: .15rem;
  color: #f8fafc;
}
.tei-entity-hover-tip .tei-entity-hover-desc {
  color: #cbd5e1;
  font-size: .78rem;
  font-style: italic;
}
.tei-entity-hover-tip .tei-entity-hover-src {
  color: #94a3b8;
  font-size: .7rem;
  margin-top: .35rem;
  letter-spacing: .02em;
}
.tei-entity-hover-tip .tei-entity-hover-loading,
.tei-entity-hover-tip .tei-entity-hover-error {
  color: #cbd5e1;
  font-style: italic;
}
/* ``tei-has-preview`` is added by the entity-hover JS at page load
   to every entity link whose @ref is resolvable by the popover
   engine (today: Wikidata; more authorities land later via the
   backend proxy). The visual distinction from a plain entity link
   is the underline style: entity base uses ``dotted`` 1px, preview-
   capable links upgrade to ``dashed`` 1.5px — a more decisive
   underline that signals "there's extra info here" without
   competing with the colour that already says "this is a link"
   and without a superscripted glyph (which in an edition looks
   like an alphabetic footnote marker). */
a.tei-persname.tei-has-preview,
a.tei-placename.tei-has-preview,
a.tei-orgname.tei-has-preview {
  border-bottom-style: dashed;
  border-bottom-width: 1.5px;
}
/* Hover state is already "solid" for every entity anchor (see the
   ``a.tei-persname:hover`` rule injected by the default XSLT), so
   preview-capable links promote dotted→dashed at rest and then both
   variants collapse to solid on hover. The popover lands on hover
   too — no need for a further distinction there. */
"""


_DEFAULT_FONT = 'Georgia,"Times New Roman",serif'

# ── Image rendering helpers ───────────────────────────────────────────────────

# Minimal modal JS injected into document pages when any layout is set to
# "modal".  Uses event delegation so it works on dynamically-added elements.
_IMAGE_MODAL_JS = """\
(function(){
var ov=document.createElement('div');
ov.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9999;cursor:zoom-out;align-items:center;justify-content:center;';
var mi=document.createElement('img');
mi.style.cssText='max-width:92vw;max-height:90vh;object-fit:contain;border-radius:4px;box-shadow:0 0 40px rgba(0,0,0,.5);';
ov.appendChild(mi);
document.body.appendChild(ov);
function open(src){mi.src=src;ov.style.display='flex';document.body.style.overflow='hidden';}
function close(){ov.style.display='none';mi.src='';document.body.style.overflow='';}
ov.addEventListener('click',close);
document.addEventListener('keydown',function(e){if(e.key==='Escape')close();});
document.addEventListener('click',function(e){
  var t=e.target;
  if(t.tagName==='IMG'&&t.closest('figure.tei-figure,figure.tei-pb-facsimile,.gallery-item')){
    e.preventDefault();open(t.src);
  }
});
})();"""


def _build_image_rendering_css(cfg: dict) -> str:
    """Return CSS override rules derived from the *image_rendering* config dict.

    Returns an empty string when image rendering is disabled or cfg is empty.
    The returned CSS is appended inside the per-page ``<style>`` block so it
    overrides the XSLT-generated defaults without touching the stylesheet.
    """
    if not cfg or not cfg.get("enabled"):
        return ""

    lines: list[str] = ["/* image-rendering overrides */"]

    fig   = cfg.get("figure", {}) or {}
    pb    = cfg.get("pb", {}) or {}
    fig_size   = fig.get("size", "full")
    fig_layout = fig.get("layout", "inline")
    pb_show    = pb.get("show", True)
    pb_size    = pb.get("size", "thumbnail")
    pb_layout  = pb.get("layout", "inline")

    # ── figure ───────────────────────────────────────────────────────────────
    if fig_size == "thumbnail":
        lines.append("figure.tei-figure{max-width:200px;}")
    if fig_layout == "left":
        lines.append(
            "figure.tei-figure{float:left;max-width:min(40%,320px);"
            "margin:0 1.5rem 1rem 0;clear:left;}"
        )
    elif fig_layout == "right":
        lines.append(
            "figure.tei-figure{float:right;max-width:min(40%,320px);"
            "margin:0 0 1rem 1.5rem;clear:right;}"
        )
    elif fig_layout == "modal":
        lines.append("figure.tei-figure img{cursor:zoom-in;}")
        if fig_size == "thumbnail":
            lines.append("figure.tei-figure{max-width:160px;}")

    # ── pb facsimile ─────────────────────────────────────────────────────────
    if not pb_show:
        lines.append("figure.tei-pb-facsimile{display:none;}")
    else:
        if pb_size == "thumbnail":
            lines.append("figure.tei-pb-facsimile{max-width:200px;margin:1rem auto;}")
        if pb_layout == "left":
            lines.append(
                "figure.tei-pb-facsimile{float:left;max-width:min(35%,260px);"
                "margin:0 1.5rem 1rem 0;clear:left;}"
            )
        elif pb_layout == "right":
            lines.append(
                "figure.tei-pb-facsimile{float:right;max-width:min(35%,260px);"
                "margin:0 0 1rem 1.5rem;clear:right;}"
            )
        elif pb_layout == "modal":
            lines.append("figure.tei-pb-facsimile img{cursor:zoom-in;}")
            if pb_size == "thumbnail":
                lines.append(
                    "figure.tei-pb-facsimile{max-width:120px;margin:1rem auto;}"
                )
        elif pb_layout == "one-to-one":
            # Facsimile figures are hidden inline; JS moves their src into the panel.
            lines.append("figure.tei-pb-facsimile{display:none!important;}")
            # Other figures become modal-clickable (modal JS handles the overlay).
            lines.append("figure.tei-figure img{cursor:zoom-in;}")
            # Full-viewport override for <main> — also applied via JS for older browsers.
            lines.append(
                "main:has(.oto-layout){"
                "max-width:100%!important;padding:0!important;margin:0!important;}"
            )
            # Two-column grid: dark image panel (left) + scrollable text (right).
            # The panel is sticky and fills the viewport area below the navbar (3.5rem).
            lines.append(
                ".oto-layout{display:grid;grid-template-columns:1fr 1fr;min-height:100vh;}"
                ".oto-panel{"
                "position:sticky;top:3.5rem;height:calc(100vh - 3.5rem);"
                "display:flex;flex-direction:column;"
                "background:#111827;overflow:hidden;}"
                # Image wrapper: fills remaining height; holds img + SVG overlay.
                ".oto-img-wrap{"
                "position:relative;flex:1;min-height:0;overflow:hidden;}"
                ".oto-img{"
                "width:100%;height:100%;"
                "object-fit:contain;display:block;"
                "padding:.75rem;box-sizing:border-box;}"
                # SVG drawn on top of the image; pointer-events:none so clicks pass through.
                # Explicit left/top/width/height because inset:0 alone is insufficient
                # for SVG elements in some browsers (SVG retains its intrinsic 300x150
                # default size unless overridden with CSS width/height).
                ".oto-zone-svg{"
                "position:absolute;left:0;top:0;"
                "width:100%;height:100%;"
                "pointer-events:none;overflow:visible;display:block;}"
                ".oto-nav{"
                "display:flex;align-items:center;justify-content:center;"
                "gap:.6rem;padding:.4rem .75rem;flex-shrink:0;"
                "border-top:1px solid #374151;background:#1f2937;}"
                ".oto-nav-btn{"
                "background:#374151;border:1px solid #4b5563;"
                "border-radius:4px;padding:.2rem .55rem;"
                "cursor:pointer;font-size:.85rem;line-height:1.4;color:#f9fafb;}"
                ".oto-nav-btn:disabled{opacity:.3;cursor:default;}"
                ".oto-nav-btn:hover:not(:disabled){background:#4b5563;}"
                ".oto-nav-counter{font-size:.75rem;color:#9ca3af;font-family:monospace;}"
                # Text column: padding restores the comfortable reading margin.
                ".oto-layout>.tei-body{padding:2rem 2.5rem 4rem;}"
                # Zone-linked word tokens: subtle dotted underline + crosshair cursor.
                ".tei-w[data-facs]{cursor:crosshair;"
                "border-bottom:1px dotted rgba(99,102,241,.45);}"
                ".tei-w[data-facs]:hover{background:rgba(99,102,241,.08);}"
                # Zone-linked line-break anchors: narrow hoverable inline block.
                ".tei-lb[data-facs]{"
                "display:inline-block;width:.8em;height:.6em;"
                "cursor:crosshair;vertical-align:middle;"
                "border-bottom:1px dotted rgba(99,102,241,.45);}"
                ".tei-lb[data-facs]:hover{background:rgba(99,102,241,.08);}"
                "@media(max-width:720px){"
                "main:has(.oto-layout){max-width:100%!important;padding:0!important;margin:0!important;}"
                ".oto-layout{display:block!important;min-height:auto;}"
                ".oto-panel{position:static;height:60vw;top:0;}"
                ".oto-layout>.tei-body{padding:1rem 1.5rem 2rem;}"
                "}"
            )

    # ── dedicated column layout (left / right) ────────────────────────────────
    # Determine which selectors need a column and which side they go to.
    # Column layout is applied by JS (_build_image_column_js); here we only emit
    # the grid CSS and sidebar style rules.
    col_selectors: list[str] = []
    col_side: str = "right"  # default; overridden below
    if fig_layout in ("column-left", "column-right"):
        col_selectors.append("figure.tei-figure")
        col_side = "left" if fig_layout == "column-left" else "right"
    if pb_show and pb_layout in ("column-left", "column-right"):
        col_selectors.append("figure.tei-pb-facsimile")
        col_side = "left" if pb_layout == "column-left" else "right"

    if col_selectors:
        # Apply the two-column grid to a wrapper div (.col-layout-wrapper) that
        # the JS creates around .tei-body only.  This avoids pulling unrelated
        # siblings of <main> (e.g. breadcrumb <nav>) into the grid.
        # position:relative is required so the optional SVG connector overlay
        # (absolutely positioned inside the wrapper) is clipped correctly.
        if col_side == "right":
            lines.append(
                ".col-layout-wrapper{position:relative;display:grid;"
                "grid-template-columns:1fr 260px;gap:2.5rem;align-items:start;}"
            )
        else:
            lines.append(
                ".col-layout-wrapper{position:relative;display:grid;"
                "grid-template-columns:260px 1fr;gap:2.5rem;align-items:start;}"
            )
        lines.append(
            ".tei-body{min-width:0;}"
            # The sidebar uses position:relative so the JS can place each figure
            # with position:absolute at the Y coordinate of its text anchor.
            ".img-sidebar{position:relative;}"
            ".img-sidebar figure{margin:0 0 1rem 0;max-width:100%;}"
            ".img-sidebar figure img{max-width:100%;height:auto;"
            "border:1px solid #e5e7eb;border-radius:3px;display:block;}"
            ".img-sidebar figcaption{font-size:.7rem;color:#9ca3af;"
            "font-family:monospace;margin-top:.25rem;text-align:center;}"
        )
        # Prevent the moved elements from showing in their inline position.
        lines.append(",".join(col_selectors) + "{display:none;}")
        lines.append(".img-sidebar figure{display:block;}")
        # Responsive: stack vertically on narrow screens.
        # On narrow screens the sidebar is hidden (images already appear inline
        # via the placeholder anchors in the text, so nothing is lost).
        lines.append(
            "@media(max-width:700px){"
            ".col-layout-wrapper{display:block!important;}"
            ".img-sidebar{display:none!important;}"
            "}"
        )
        # Connector toggle button — only emitted when the feature is enabled.
        if cfg.get("column_connectors"):
            lines.append(
                ".col-connectors-btn{"
                "position:fixed;bottom:1.25rem;right:1.25rem;z-index:50;"
                "background:#1e293b;color:#f8fafc;border:none;border-radius:6px;"
                "padding:.4rem .85rem;font-size:.75rem;cursor:pointer;"
                "opacity:.8;box-shadow:0 1px 6px rgba(0,0,0,.25);"
                "}"
                ".col-connectors-btn:hover{opacity:1;}"
            )

    # ── facsimile gallery ─────────────────────────────────────────────────────
    if cfg.get("facsimile_gallery"):
        lines.append(
            ".facsimile-gallery{margin:1.5rem 0;padding:1rem;"
            "border:1px solid #e5e7eb;border-radius:4px;background:#fafafa;}"
            ".facsimile-gallery h3{font-size:.8rem;color:#6b7280;margin:0 0 .75rem;"
            "text-transform:uppercase;letter-spacing:.06em;}"
            ".gallery-grid{display:flex;flex-wrap:wrap;gap:.75rem;}"
            ".gallery-item{margin:0;text-align:center;}"
            ".gallery-item img{width:100px;height:100px;object-fit:cover;"
            "border:1px solid #e5e7eb;border-radius:3px;display:block;cursor:zoom-in;}"
            "figcaption.gallery-caption{font-size:.65rem;color:#9ca3af;"
            "font-family:monospace;margin-top:.2rem;}"
        )

    return "\n".join(lines) if len(lines) > 1 else ""


def _build_image_column_js(cfg: dict) -> str:
    """Return JS that moves images into a dedicated sidebar column, vertically
    anchored to their citation point in the text.

    Strategy:
    1. Figures are hidden by CSS (``display:none``) to prevent inline layout.
       Their ``getBoundingClientRect()`` returns zeros, so we cannot measure
       their positions directly.
    2. Before building the wrapper/sidebar we insert a zero-size ``<span>``
       placeholder immediately before each figure.  Placeholders are not
       subject to the CSS ``display:none`` rule and therefore report correct
       viewport coordinates, marking the exact text line where each figure is
       cited.
    3. We build the ``.col-layout-wrapper`` grid, measure each placeholder's
       Y position relative to the wrapper top, then append each figure to the
       sidebar with ``position:absolute; top:<measured>px``.
    4. The sidebar's ``min-height`` is stretched to fit the lowest figure.
    5. When ``column_connectors`` is enabled, an SVG overlay is drawn inside
       the wrapper with a dashed bezier curve for each figure connecting its
       text anchor to the sidebar image.  A fixed toggle button lets the reader
       show/hide all connectors.
    """
    if not cfg or not cfg.get("enabled"):
        return ""

    fig    = cfg.get("figure", {}) or {}
    pb     = cfg.get("pb", {}) or {}
    fig_layout = fig.get("layout", "inline")
    pb_show    = pb.get("show", True)
    pb_layout  = pb.get("layout", "inline")

    selectors: list[str] = []
    side: str = "right"
    if fig_layout in ("column-left", "column-right"):
        selectors.append("figure.tei-figure")
        side = "left" if fig_layout == "column-left" else "right"
    if pb_show and pb_layout in ("column-left", "column-right"):
        selectors.append("figure.tei-pb-facsimile")
        side = "left" if pb_layout == "column-left" else "right"

    if not selectors:
        return ""

    connectors: bool = bool(cfg.get("column_connectors"))
    sel_js = ",".join(selectors)

    # Side-specific JS expressions for connector endpoints (evaluated at build
    # time so no branching is needed in the emitted JS).
    # x1 = edge of the text column facing the sidebar.
    # x2 = edge of the sidebar facing the text column.
    if side == "right":
        x1_js  = "Math.round(bodyRect.right-wRect.left)"
        x2_js  = "Math.round(sbRect.left-wRect.left)"
        cp1_js = "x1+dx"
        cp2_js = "x2-dx"
    else:
        x1_js  = "Math.round(bodyRect.left-wRect.left)"
        x2_js  = "Math.round(sbRect.right-wRect.left)"
        cp1_js = "x1-dx"
        cp2_js = "x2+dx"

    js = (
        "(function(){"
        "var body=document.querySelector('.tei-body');"
        "if(!body)return;"
        f"var figs=Array.prototype.slice.call(body.querySelectorAll('{sel_js}'));"
        "if(!figs.length)return;"
        # Insert zero-size placeholders before each figure while they are still
        # in the text flow.  Figures are display:none (CSS), so placeholders are
        # the only elements whose getBoundingClientRect() gives a valid Y.
        "var anchors=figs.map(function(f){"
        "var a=document.createElement('span');"
        "a.style.cssText='display:inline;width:0;height:0;overflow:hidden;pointer-events:none;';"
        "f.parentNode.insertBefore(a,f);"
        "return a;"
        "});"
        # Build wrapper and sidebar.
        "var wrapper=document.createElement('div');"
        "wrapper.className='col-layout-wrapper';"
        "body.parentNode.insertBefore(wrapper,body);"
        "wrapper.appendChild(body);"
        "var sb=document.createElement('div');"
        "sb.className='img-sidebar';"
        "sb.style.position='relative';"
        f"if('{side}'==='right'){{wrapper.appendChild(sb);}}else{{wrapper.insertBefore(sb,body);}}"
        # Force a layout pass so getBoundingClientRect values are current.
        "void wrapper.offsetHeight;"
        # Capture the wrapper rect once; wRect.top is used for Y anchoring and
        # wRect.left for X connector endpoints.  Both cancel scroll offset.
        "var wRect=wrapper.getBoundingClientRect();"
        "var wTop=wRect.top;"
        # Place each figure at the Y coordinate of its text anchor.
        "figs.forEach(function(f,i){"
        "var top=Math.max(0,Math.round(anchors[i].getBoundingClientRect().top-wTop));"
        "f.style.position='absolute';"
        "f.style.top=top+'px';"
        "f.style.left='0';"
        "f.style.right='0';"
        "f.style.display='block';"
        "sb.appendChild(f);"
        "});"
        # Stretch the sidebar so absolutely-positioned figures are not clipped.
        "void sb.offsetHeight;"
        "var maxBottom=0;"
        "figs.forEach(function(f){"
        "maxBottom=Math.max(maxBottom,parseInt(f.style.top,10)+f.offsetHeight);"
        "});"
        "sb.style.minHeight=maxBottom+'px';"
    )

    if connectors:
        js += (
            # Re-measure after layout is stable (figures are now placed).
            "void wrapper.offsetHeight;"
            "var bodyRect=body.getBoundingClientRect();"
            "var sbRect=sb.getBoundingClientRect();"
            # SVG overlay covers the full wrapper height so curves are never clipped.
            "var svg=document.createElementNS('http://www.w3.org/2000/svg','svg');"
            "svg.setAttribute('class','col-connectors');"
            "svg.style.cssText='position:absolute;top:0;left:0;width:100%;"
            "overflow:visible;pointer-events:none;';"
            "svg.style.height=maxBottom+'px';"
            "wrapper.appendChild(svg);"
            # Draw a dashed cubic bezier for each anchor → figure pair.
            "figs.forEach(function(f,i){"
            "var aY=Math.round(anchors[i].getBoundingClientRect().top-wRect.top);"
            "var fCY=parseInt(f.style.top,10)+Math.round(f.offsetHeight/2);"
            f"var x1={x1_js};"
            f"var x2={x2_js};"
            "var dx=Math.round(Math.abs(x2-x1)*0.45);"
            f"var cp1x={cp1_js};"
            f"var cp2x={cp2_js};"
            "var d='M'+x1+','+aY+' C'+cp1x+','+aY+' '+cp2x+','+fCY+' '+x2+','+fCY;"
            "var p=document.createElementNS('http://www.w3.org/2000/svg','path');"
            "p.setAttribute('d',d);"
            "p.setAttribute('fill','none');"
            "p.setAttribute('stroke','#94a3b8');"
            "p.setAttribute('stroke-width','1.5');"
            "p.setAttribute('stroke-dasharray','4,3');"
            "p.setAttribute('opacity','0.75');"
            "svg.appendChild(p);"
            "});"
            # Fixed toggle button — appended to <body> so it sits above all content.
            "var shown=true;"
            "var btn=document.createElement('button');"
            "btn.className='col-connectors-btn';"
            "btn.textContent='Hide connections';"
            "document.body.appendChild(btn);"
            "btn.addEventListener('click',function(){"
            "shown=!shown;"
            "svg.style.display=shown?'':'none';"
            "btn.textContent=shown?'Hide connections':'Show connections';"
            "});"
        )

    js += "})();"
    return js


def _build_one_to_one_js(cfg: dict) -> str:
    """Return JS that sets up the one-to-one facsimile viewer layout.

    Two-column layout: sticky image panel on the left (showing the current
    facsimile page), scrollable document text on the right.
    IntersectionObserver updates the panel image automatically as the reader
    scrolls through ``<pb facs>`` boundaries.  Prev/next buttons allow manual
    navigation.  All ``<figure class="tei-figure">`` images remain as modal
    triggers (their cursor:zoom-in CSS is set by _build_image_rendering_css;
    _IMAGE_MODAL_JS handles the actual overlay).
    """
    if not cfg or not cfg.get("enabled"):
        return ""
    pb = cfg.get("pb", {}) or {}
    if pb.get("layout") != "one-to-one":
        return ""

    return (
        "(function(){"
        "var body=document.querySelector('.tei-body');"
        "if(!body)return;"
        # Collect facsimile figures in document order.
        "var figs=Array.prototype.slice.call(body.querySelectorAll('figure.tei-pb-facsimile'));"
        "if(!figs.length)return;"
        # Extract the src of each figure's <img> (figures are display:none via CSS;
        # their img.src is still accessible before they are moved to the panel).
        "var pages=figs.map(function(f){"
        "var img=f.querySelector('img');"
        "return{src:img?img.src:'',fig:f};"
        "});"
        # Insert invisible zero-height anchors immediately before each figure so
        # IntersectionObserver has something to watch (display:none elements have
        # no layout and getBoundingClientRect() returns zeros).
        "var anchors=pages.map(function(p,i){"
        "var a=document.createElement('span');"
        "a.style.cssText='display:block;height:0;overflow:hidden;';"
        "a.dataset.otoIdx=String(i);"
        "p.fig.parentNode.insertBefore(a,p.fig);"
        "return a;"
        "});"
        # Parse zone coordinate data embedded by the XSLT in a JSON script element.
        # Result is a flat map { zone_id: {ulx,uly,lrx,lry} }.
        "var zoneMap={};"
        "var zoneScript=document.getElementById('tei-facsimile-zones');"
        "if(zoneScript){"
        "try{zoneMap=JSON.parse(zoneScript.textContent||zoneScript.innerText||'{}');}"
        "catch(e){}"
        "}"
        # Capture <main> before moving body — needed for the full-width override.
        "var mainEl=body.parentNode;"
        # Build the two-column wrapper grid.
        "var layout=document.createElement('div');"
        "layout.className='oto-layout';"
        "body.parentNode.insertBefore(layout,body);"
        # Override <main>'s max-width / padding so the grid spans the full viewport.
        # (CSS :has() is the declarative version; this JS path covers older browsers.)
        "if(mainEl){"
        "mainEl.style.maxWidth='100%';"
        "mainEl.style.padding='0';"
        "mainEl.style.margin='0';"
        "}"
        # Build the image panel (left column).
        "var panel=document.createElement('div');"
        "panel.className='oto-panel';"
        "var imgEl=document.createElement('img');"
        "imgEl.className='oto-img';"
        "imgEl.alt='';"
        # SVG overlay — drawn on top of the image to highlight zone rectangles.
        # Use setAttribute('class',...) instead of .className because SVG elements
        # expose className as SVGAnimatedString, not a plain string.
        "var svgNS='http://www.w3.org/2000/svg';"
        "var svgEl=document.createElementNS(svgNS,'svg');"
        "svgEl.setAttribute('class','oto-zone-svg');"
        "svgEl.setAttribute('aria-hidden','true');"
        # Wrapper div keeps img and SVG in the same stacking context.
        "var imgWrap=document.createElement('div');"
        "imgWrap.className='oto-img-wrap';"
        "imgWrap.appendChild(imgEl);"
        "imgWrap.appendChild(svgEl);"
        # Navigation bar: ← counter →
        "var nav=document.createElement('div');"
        "nav.className='oto-nav';"
        "var prevBtn=document.createElement('button');"
        "prevBtn.className='oto-nav-btn';"
        "prevBtn.innerHTML='&#8592;';"
        "var counter=document.createElement('span');"
        "counter.className='oto-nav-counter';"
        "var nextBtn=document.createElement('button');"
        "nextBtn.className='oto-nav-btn';"
        "nextBtn.innerHTML='&#8594;';"
        "nav.appendChild(prevBtn);nav.appendChild(counter);nav.appendChild(nextBtn);"
        "panel.appendChild(imgWrap);panel.appendChild(nav);"
        # Left panel first, text body second.
        "layout.appendChild(panel);layout.appendChild(body);"
        # Zone highlight helpers.
        "function clearZone(){"
        "while(svgEl.firstChild)svgEl.removeChild(svgEl.firstChild);"
        "}"
        # Draw a zone rectangle on the SVG overlay, accounting for object-fit:contain
        # letterboxing and the padding on the <img> element.
        # Coordinates are computed in the SVG element's own client space (svgEl.clientWidth /
        # clientHeight) rather than via getBoundingClientRect offsets, so the calculation
        # works correctly even when the page has CSS transforms or fractional DPR scaling.
        "function showZone(zid){"
        "clearZone();"
        "var z=zoneMap[zid];"
        "if(!z){console.log('[oto-zones] zone not found:',zid,'keys:',Object.keys(zoneMap));return;}"
        "var nw=imgEl.naturalWidth,nh=imgEl.naturalHeight;"
        "if(!nw||!nh){console.log('[oto-zones] image not loaded yet, nw=',nw,'nh=',nh);return;}"
        "var st=window.getComputedStyle(imgEl);"
        "var pt=parseFloat(st.paddingTop)||0,pr=parseFloat(st.paddingRight)||0;"
        "var pb=parseFloat(st.paddingBottom)||0,pl=parseFloat(st.paddingLeft)||0;"
        "var cw=imgEl.clientWidth-pl-pr,ch=imgEl.clientHeight-pt-pb;"
        "if(cw<=0||ch<=0)return;"
        "var ia=nw/nh,ba=cw/ch,rw,rh,ox,oy;"
        "if(ba>ia){rh=ch;rw=rh*ia;ox=(cw-rw)/2;oy=0;}"
        "else{rw=cw;rh=rw/ia;ox=0;oy=(ch-rh)/2;}"
        "var sx=rw/nw,sy=rh/nh;"
        # The SVG covers the same area as the img (both fill imgWrap).
        # Base offsets: padding + letterboxing offset within the SVG coordinate space.
        "var bx=pl+ox,by=pt+oy;"
        "var rect=document.createElementNS(svgNS,'rect');"
        "rect.setAttribute('x',bx+z.ulx*sx);"
        "rect.setAttribute('y',by+z.uly*sy);"
        "rect.setAttribute('width',(z.lrx-z.ulx)*sx);"
        "rect.setAttribute('height',(z.lry-z.uly)*sy);"
        "rect.setAttribute('fill','rgba(99,102,241,.20)');"
        "rect.setAttribute('stroke','#6366f1');"
        "rect.setAttribute('stroke-width','2');"
        "rect.setAttribute('rx','3');"
        "svgEl.appendChild(rect);"
        "}"
        # State.
        "var cur=0;"
        "function goTo(i){"
        "cur=i;"
        "imgEl.src=pages[i].src;"
        "counter.textContent=(i+1)+' / '+pages.length;"
        "prevBtn.disabled=i===0;"
        "nextBtn.disabled=i===pages.length-1;"
        "clearZone();"
        "}"
        "goTo(0);"
        # If the user hovers before the image finishes loading, naturalWidth/naturalHeight
        # are 0 and showZone returns early.  Re-draw the active zone once it loads.
        "imgEl.addEventListener('load',function(){if(activeZone)showZone(activeZone);});"
        # Debug: log zone map size so the browser console shows whether data arrived.
        "console.log('[oto-zones]',Object.keys(zoneMap).length,'zones loaded',"
        "Object.keys(zoneMap).slice(0,5));"
        # Manual prev / next — scroll the corresponding anchor into view.
        "prevBtn.addEventListener('click',function(){"
        "if(cur>0){cur--;goTo(cur);"
        "anchors[cur].scrollIntoView({behavior:'smooth',block:'start'});}"
        "});"
        "nextBtn.addEventListener('click',function(){"
        "if(cur<pages.length-1){cur++;goTo(cur);"
        "anchors[cur].scrollIntoView({behavior:'smooth',block:'start'});}"
        "});"
        # Zone hover via event delegation on the text column.
        # Walks up from the event target to find the nearest [data-facs] ancestor.
        # Keeps the active zone stable while moving within the same element.
        "var activeZone=null;"
        "body.addEventListener('mouseover',function(e){"
        "var el=e.target;"
        "while(el&&el!==body){"
        "if(el.dataset&&el.dataset.facs){"
        "if(el.dataset.facs!==activeZone){"
        "activeZone=el.dataset.facs;"
        "showZone(activeZone);}"
        "return;}"
        "el=el.parentElement;}"
        "if(activeZone){activeZone=null;clearZone();}"
        "});"
        "body.addEventListener('mouseleave',function(){"
        "activeZone=null;clearZone();"
        "});"
        # IntersectionObserver: track which anchors are in the top 60 % of the
        # viewport and show the image for the first (earliest) visible one.
        # rootMargin '0px 0px -40% 0px' means an anchor only counts as
        # 'intersecting' when it is above the 60 % mark of the viewport height.
        "if(typeof IntersectionObserver!=='undefined'){"
        "var vis={};"
        "var obs=new IntersectionObserver(function(entries){"
        "entries.forEach(function(e){"
        "vis[e.target.dataset.otoIdx]=e.isIntersecting;"
        "});"
        "var first=-1;"
        "for(var k in vis){"
        "if(vis[k]){var ki=parseInt(k,10);"
        "if(first===-1||ki<first)first=ki;}"
        "}"
        "if(first!==-1&&first!==cur)goTo(first);"
        "},{rootMargin:'0px 0px -40% 0px',threshold:0});"
        "anchors.forEach(function(a){obs.observe(a);});"
        "}"
        "})();"
    )


def _build_note_rendering_css(cfg: dict) -> str:
    """Return CSS overrides for the note display mode.

    For ``end-of-text`` (the default XSLT output) no override is needed.
    For ``tooltip`` the aside is hidden and a tooltip element is styled.
    For ``frame`` the aside is hidden and a fixed side panel is styled.
    """
    if not cfg or not cfg.get("enabled"):
        return ""
    mode: str = cfg.get("mode", "end-of-text")
    if mode == "tooltip":
        return (
            # Tooltip container positioned relative to its superscript.
            "sup.tei-note-ref{position:relative;}"
            ".tei-note-tooltip{"
            "display:none;position:absolute;bottom:1.6em;left:50%;"
            "transform:translateX(-50%);"
            "background:#1e293b;color:#f8fafc;font-size:.78rem;"
            "line-height:1.55;padding:.4rem .65rem;border-radius:5px;"
            "min-width:200px;max-width:320px;z-index:200;"
            "white-space:normal;font-style:normal;pointer-events:none;"
            "box-shadow:0 2px 10px rgba(0,0,0,.3);"
            "}"
            ".tei-note-tooltip::after{"
            "content:'';position:absolute;top:100%;left:50%;"
            "transform:translateX(-50%);"
            "border:5px solid transparent;border-top-color:#1e293b;"
            "}"
            "sup.tei-note-ref:hover .tei-note-tooltip{display:block;}"
            # Hide the default notes section (used as data source by JS only).
            "aside.tei-notes-section{display:none;}"
        )
    if mode == "frame":
        return (
            "aside.tei-notes-section{display:none;}"
            ".tei-notes-frame{"
            "position:fixed;right:0;top:0;width:290px;height:100vh;"
            "overflow-y:auto;background:#f9fafb;border-left:1px solid #e5e7eb;"
            "padding:1rem;z-index:40;font-size:.82rem;display:none;"
            "box-shadow:-2px 0 8px rgba(0,0,0,.06);"
            "}"
            ".tei-notes-frame.open{display:block;}"
            ".tei-notes-frame-hdr{"
            "display:flex;justify-content:space-between;align-items:center;"
            "margin-bottom:.75rem;border-bottom:1px solid #e5e7eb;padding-bottom:.5rem;"
            "}"
            ".tei-notes-frame-title{"
            "font-size:.72rem;font-weight:600;text-transform:uppercase;"
            "letter-spacing:.06em;color:#374151;"
            "}"
            ".tei-notes-frame-close{"
            "background:none;border:none;cursor:pointer;color:#9ca3af;font-size:1rem;padding:0;"
            "}"
            ".tei-notes-frame-close:hover{color:#374151;}"
            ".tei-note-frame-entry{"
            "padding:.35rem 0;border-bottom:1px solid #f3f4f6;line-height:1.55;"
            "display:flex;gap:.4rem;"
            "}"
            ".tei-note-frame-entry.highlighted{background:#fffbeb;border-radius:3px;padding-left:.3rem;}"
            ".tei-note-frame-lbl{flex-shrink:0;font-weight:600;color:#6b7280;min-width:1.4rem;}"
            ".tei-note-frame-body{flex:1;color:#374151;}"
            "body.has-frame{margin-right:305px;transition:margin-right .2s;}"
        )
    return ""  # end-of-text: XSLT default styling is sufficient


def _build_note_rendering_js(cfg: dict) -> str:
    """Return JS for tooltip or frame note display modes.

    The script reads note content from the ``<aside class="tei-notes-section">``
    generated by the XSLT and transforms it into the selected display mode.
    """
    if not cfg or not cfg.get("enabled"):
        return ""
    mode: str = cfg.get("mode", "end-of-text")
    if mode == "tooltip":
        return (
            "(function(){"
            # For each note marker, find its note entry in the aside and
            # create an inline tooltip child.
            "document.querySelectorAll('sup.tei-note-ref').forEach(function(sup){"
            "var a=sup.querySelector('a.tei-note-link');"
            "if(!a)return;"
            "var entry=document.querySelector(a.getAttribute('href'));"
            "if(!entry)return;"
            "var body=entry.querySelector('.tei-note-body');"
            "if(!body)return;"
            "var tip=document.createElement('span');"
            "tip.className='tei-note-tooltip';"
            "tip.innerHTML=body.innerHTML;"
            "sup.appendChild(tip);"
            # Click toggles visibility (mobile-friendly).
            "a.addEventListener('click',function(e){"
            "e.preventDefault();"
            "tip.style.display=tip.style.display==='block'?'none':'block';"
            "});"
            "});"
            # Clicking outside closes all open tooltips.
            "document.addEventListener('click',function(e){"
            "if(!e.target.closest('sup.tei-note-ref')){"
            "document.querySelectorAll('.tei-note-tooltip').forEach(function(t){"
            "t.style.display='none';});"
            "}"
            "});"
            "})();"
        )
    if mode == "frame":
        return (
            "(function(){"
            # Bail early on pages with no notes (home, browse, bibliography,
            # search, …). The build pipeline ships this script into every
            # page's <script> bundle for code-size reasons; the doc-only
            # CSS that hides the panel by default isn't loaded elsewhere,
            # so without this guard the panel header would render visible
            # in the bottom-left of every non-doc page.
            "var aside=document.querySelector('.tei-notes-section');"
            "if(!aside)return;"
            # Build the frame panel.
            "var frame=document.createElement('div');"
            "frame.className='tei-notes-frame';"
            "var hdr=document.createElement('div');"
            "hdr.className='tei-notes-frame-hdr';"
            "var ttl=document.createElement('span');"
            "ttl.className='tei-notes-frame-title';"
            "ttl.textContent='Notes';"
            "var cls=document.createElement('button');"
            "cls.className='tei-notes-frame-close';"
            "cls.setAttribute('aria-label','Close notes panel');"
            "cls.textContent='✕';"
            "cls.addEventListener('click',function(){"
            "frame.classList.remove('open');"
            "document.body.classList.remove('has-frame');"
            "});"
            "hdr.appendChild(ttl);hdr.appendChild(cls);frame.appendChild(hdr);"
            # Populate frame from the aside (used as data source).
            "aside.querySelectorAll('.tei-note-entry').forEach(function(entry){"
            "var fe=document.createElement('div');"
            "fe.className='tei-note-frame-entry';"
            "fe.dataset.noteId=entry.id;"
            "var lbl=entry.querySelector('.tei-note-back');"
            "var bdy=entry.querySelector('.tei-note-body');"
            "var lb=document.createElement('span');"
            "lb.className='tei-note-frame-lbl';"
            "if(lbl)lb.textContent=lbl.textContent.trim();"
            "var bd=document.createElement('span');"
            "bd.className='tei-note-frame-body';"
            "if(bdy)bd.innerHTML=bdy.innerHTML;"
            "fe.appendChild(lb);fe.appendChild(bd);"
            "frame.appendChild(fe);"
            "});"
            "document.body.appendChild(frame);"
            # Clicking a note marker opens the frame and highlights the entry.
            "document.querySelectorAll('sup.tei-note-ref a.tei-note-link').forEach(function(a){"
            "a.addEventListener('click',function(e){"
            "e.preventDefault();"
            "var noteId=a.getAttribute('href').substring(1);" # "note-xxx"
            "frame.classList.add('open');"
            "document.body.classList.add('has-frame');"
            "frame.querySelectorAll('.tei-note-frame-entry').forEach(function(fe){"
            "fe.classList.remove('highlighted');});"
            "var target=frame.querySelector('[data-note-id=\"'+noteId+'\"]');"
            "if(target){"
            "target.classList.add('highlighted');"
            "target.scrollIntoView({behavior:'smooth',block:'nearest'});"
            "}"
            "});"
            "});"
            "})();"
        )
    return ""  # end-of-text: no JS needed


def _build_entity_hover_js(cfg: dict | None) -> str:
    """Return JS that enables Wikidata hover previews on entity links.

    When ``xslt_config.entity_hover.enabled`` is true on the website,
    this JS is appended to the page's ``custom_js``. It attaches a
    single delegated ``mouseover`` / ``mouseout`` listener to the
    document, filters for ``<a class="tei-persname|tei-placename|
    tei-orgname">`` with a ``href`` pointing at Wikidata
    (``wikidata.org/wiki/Qxxx`` or ``wikidata.org/entity/Qxxx``), and
    on a 200-ms dwell opens a small popover populated from
    ``wbgetentities`` — label, description and the first P18 image
    when present. Results are cached per-session in a module-scope
    object so repeated hovers on the same Q-ID don't re-fetch.

    Scope is MVP-limited to Wikidata because its API exposes open
    CORS (``origin=*``) and no key is needed; other authorities
    (ORCID, GeoNames, ROR, VIAF, GND, Getty AAT) block cross-origin
    browser calls and would need a backend proxy — planned for a
    follow-up. Feature is opt-in per site because hovering over any
    entity link triggers an HTTP request to a third-party service,
    which some deployments prefer to advertise to visitors first.
    """
    if not cfg or not cfg.get("enabled"):
        return ""
    return (
        "(function(){"
        "var cache={};"
        "var currentTip=null;"
        "var hoverTimer=null;"
        # Supports both common URL shapes: /wiki/Q123 and /entity/Q123.
        "var WD_RE=/wikidata\\.org\\/(?:wiki|entity)\\/(Q[0-9]+)/i;"
        "var lang=(document.documentElement.lang||'en').split('-')[0];"
        "var langs=lang==='en'?'en':(lang+'|en');"
        "var selectors='a.tei-persname,a.tei-placename,a.tei-orgname';"
        "function escHtml(s){return String(s).replace(/[&<>\"']/g,function(c){"
        "return ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'})[c];});}"
        "function extractQid(href){if(!href)return null;"
        "var m=href.match(WD_RE);return m?m[1]:null;}"
        "function fetchEntity(qid){"
        "if(cache[qid])return Promise.resolve(cache[qid]);"
        "var url='https://www.wikidata.org/w/api.php?action=wbgetentities&ids='+qid+"
        "'&props=labels|descriptions|claims&languages='+langs+"
        "'&format=json&origin=*';"
        "return fetch(url).then(function(r){return r.json();}).then(function(data){"
        "var ent=data.entities&&data.entities[qid];if(!ent)return null;"
        "var L=ent.labels||{};var D=ent.descriptions||{};"
        "var label=((L[lang]||L.en)||{}).value||qid;"
        "var desc=((D[lang]||D.en)||{}).value||'';"
        "var thumb=null;"
        "try{if(ent.claims&&ent.claims.P18&&ent.claims.P18[0]){"
        "var fn=ent.claims.P18[0].mainsnak.datavalue.value;"
        "thumb='https://commons.wikimedia.org/wiki/Special:FilePath/'+"
        "encodeURIComponent(fn)+'?width=240';}}catch(e){}"
        "var result={label:label,desc:desc,thumb:thumb};"
        "cache[qid]=result;return result;"
        "}).catch(function(){return null;});}"
        "function positionTip(tip,target){"
        "var rect=target.getBoundingClientRect();"
        "tip.style.top=(rect.bottom+window.scrollY+6)+'px';"
        "tip.style.left=(rect.left+window.scrollX)+'px';"
        # If tooltip overflows viewport right, shift it left
        "var tr=tip.getBoundingClientRect();"
        "var ov=tr.right-window.innerWidth;"
        "if(ov>0){tip.style.left=(rect.left+window.scrollX-ov-12)+'px';}}"
        "function removeTip(){if(currentTip){currentTip.remove();currentTip=null;}}"
        "function showTip(target,qid){"
        "removeTip();"
        "var tip=document.createElement('div');"
        "tip.className='tei-entity-hover-tip';"
        "tip.innerHTML='<div class=\"tei-entity-hover-loading\">\\u2026</div>';"
        "document.body.appendChild(tip);"
        "positionTip(tip,target);currentTip=tip;"
        "fetchEntity(qid).then(function(data){"
        "if(currentTip!==tip)return;"
        "if(!data){tip.innerHTML='<div class=\"tei-entity-hover-error\">Wikidata: '+escHtml(qid)+'</div>';positionTip(tip,target);return;}"
        "var h='';"
        "if(data.thumb){h+='<img class=\"tei-entity-hover-img\" src=\"'+escHtml(data.thumb)+'\" alt=\"\">';}"
        "h+='<div class=\"tei-entity-hover-label\">'+escHtml(data.label)+'</div>';"
        "if(data.desc){h+='<div class=\"tei-entity-hover-desc\">'+escHtml(data.desc)+'</div>';}"
        "h+='<div class=\"tei-entity-hover-src\">Wikidata \\u00b7 '+escHtml(qid)+'</div>';"
        "tip.innerHTML=h;positionTip(tip,target);});}"
        "document.addEventListener('mouseover',function(e){"
        "var a=e.target.closest&&e.target.closest(selectors);"
        "if(!a)return;"
        "var qid=extractQid(a.getAttribute('href'));if(!qid)return;"
        "clearTimeout(hoverTimer);"
        "hoverTimer=setTimeout(function(){showTip(a,qid);},200);});"
        "document.addEventListener('mouseout',function(e){"
        "var a=e.target.closest&&e.target.closest(selectors);"
        "if(!a)return;"
        "var to=e.relatedTarget;"
        "if(to&&(a.contains(to)||(currentTip&&currentTip.contains(to))))return;"
        "clearTimeout(hoverTimer);removeTip();});"
        "window.addEventListener('scroll',removeTip,{passive:true});"
        # Tag every entity anchor whose href the engine can resolve, so
        # CSS can show a small ⓘ glyph next to it. Runs once at load —
        # future authorities will plug into the same ``supported``
        # probe when their regexes are added.
        "function supported(href){return !!extractQid(href);}"
        "function tagPreviewLinks(root){"
        "(root||document).querySelectorAll(selectors).forEach(function(a){"
        "if(supported(a.getAttribute('href'))){a.classList.add('tei-has-preview');}"
        "});}"
        "if(document.readyState==='loading'){"
        "document.addEventListener('DOMContentLoaded',function(){tagPreviewLinks();});"
        "}else{tagPreviewLinks();}"
        "})();"
    )


def _inject_facsimile_gallery(doc_body: str, xml_bytes: bytes) -> str:
    """Prepend a facsimile thumbnail gallery to *doc_body*.

    Parses *xml_bytes* (a TEI document from eXist-db) to collect all
    ``<surface xml:id="…"><graphic url="…"/>`` entries from the
    ``<facsimile>`` block and renders them as a ``.facsimile-gallery`` div.

    The media API URLs are *not* rewritten here; the caller's URL-rewrite step
    runs after this function and handles them uniformly.

    Returns *doc_body* unchanged when no surfaces are found or the XML is
    malformed.
    """
    try:
        # eXist holds Editor-authored TEI; not a trust boundary against
        # XXE. See public_view.py for the same hardening rationale.
        _safe_parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        root = etree.fromstring(xml_bytes, parser=_safe_parser)
    except etree.XMLSyntaxError:
        return doc_body

    tei_ns = "http://www.tei-c.org/ns/1.0"
    xml_ns = "http://www.w3.org/XML/1998/namespace"
    surfaces = root.findall(f".//{{{tei_ns}}}facsimile/{{{tei_ns}}}surface")
    if not surfaces:
        return doc_body

    items: list[str] = []
    for surface in surfaces:
        surf_id = surface.get(f"{{{xml_ns}}}id", "")
        graphic = surface.find(f"{{{tei_ns}}}graphic")
        if graphic is None:
            continue
        url = graphic.get("url", "")
        if not url:
            continue
        esc_url = _html.escape(url)
        esc_id  = _html.escape(surf_id)
        items.append(
            f'<figure class="gallery-item">'
            f'<img src="{esc_url}" alt="{esc_id}" loading="lazy"/>'
            f'<figcaption class="gallery-caption">#{esc_id}</figcaption>'
            f'</figure>'
        )

    if not items:
        return doc_body

    gallery = (
        '<div class="facsimile-gallery">'
        '<h3>Facsimile</h3>'
        '<div class="gallery-grid">' + "".join(items) + "</div>"
        "</div>"
    )
    return gallery + doc_body


def _doc_actions_toolbar(slug: str, filename: str) -> str:
    """Two-button toolbar prepended to every rendered doc page.

    'Scarica TEI' downloads the raw XML from the source endpoint;
    'Scarica PDF' triggers ``window.print()`` so the visitor's
    browser can save the page as a PDF (Chrome / Firefox / Safari /
    Edge all show "Save as PDF" as a default print destination).

    The toolbar uses the ``.doc-actions`` class which is hidden in
    print media — that way the rendered PDF never contains the
    buttons themselves.
    """
    safe_filename = _html.escape(filename, quote=True)
    src_href = f"/sites/{_html.escape(slug, quote=True)}/docs/{safe_filename}/source"
    return (
        '<div class="doc-actions">'
        f'<a class="doc-action doc-action-tei" href="{src_href}" '
        f'download="{safe_filename}">⬇ Scarica TEI</a>'
        '<button type="button" class="doc-action doc-action-pdf" '
        'onclick="window.print()">⬇ Scarica PDF</button>'
        '</div>'
    )


def _readable_text_on(bg_hex: str) -> str | None:
    """Return a light or dark text colour that reads well on *bg_hex*.

    Uses the sRGB relative-luminance formula from WCAG 2.0 G18 and
    returns ``"#e5e7eb"`` (slate-200) for dark backgrounds or
    ``"#1f2937"`` (slate-800) for light ones. Returns ``None`` when
    the input is not a parseable 3- or 6-digit hex — the caller
    falls back to a neutral default in that case.
    """
    h = (bg_hex or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return None

    def _linear(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)
    return "#1f2937" if lum > 0.5 else "#e5e7eb"


def _style_block(
    theme: dict,
    custom_css: str | None = None,
    extra_css: str | None = None,
) -> str:
    primary = _html.escape(theme.get("primary_color", "#1e293b"))
    text = _html.escape(theme.get("text_color", "#1e293b"))
    bg = _html.escape(theme.get("bg_color", "#ffffff"))
    # Banner defaults: same primary as navbar background, white text for contrast
    doc_banner_bg = _html.escape(theme.get("doc_banner_bg", primary))
    doc_banner_text = _html.escape(theme.get("doc_banner_text", "#ffffff"))
    # Font family — sanitize to strip HTML injection chars but keep CSS syntax intact
    font = re.sub(r"[<>&]", "", theme.get("font_family", _DEFAULT_FONT) or _DEFAULT_FONT)
    # Footer colours — the background is Designer-chosen; the foreground
    # is auto-derived from the background luminance so text stays
    # readable whatever hue the Designer picks. When the bg is unset /
    # transparent we fall back to the historical muted-grey default
    # which reads well against both white and most dark page bgs.
    footer_bg_raw = (theme.get("footer_bg") or "").strip()
    footer_bg = _html.escape(footer_bg_raw) if footer_bg_raw else "transparent"
    if footer_bg_raw:
        footer_color = _readable_text_on(footer_bg_raw) or "#9ca3af"
    else:
        footer_color = "#9ca3af"
    root_vars = (
        f":root{{--primary:{primary};--text:{text};--bg:{bg};"
        f"--doc-banner-bg:{doc_banner_bg};--doc-banner-text:{doc_banner_text};"
        f"--font:{font};--footer-bg:{footer_bg};--footer-text:{footer_color};}}"
    )
    # Fixed header: pin the site navbar (direct child <header> of <body>) to the
    # viewport top and add body padding so content starts below it (3.5rem = 56px).
    # Using "body > header" avoids matching <header> elements inside document content.
    fixed_header_css = (
        "\n/* fixed-header */\n"
        "body>header{position:fixed;top:0;left:0;right:0;z-index:200;}"
        "body{padding-top:3.5rem;}"
    ) if theme.get("fixed_header") else ""
    # Custom CSS is trusted Designer input; strip </style> to prevent tag break.
    custom = f"\n/* custom */\n{custom_css.replace('</style>', '')}" if custom_css else ""
    # extra_css is builder-generated (image-rendering overrides) — already safe.
    extra = f"\n{extra_css}" if extra_css else ""
    return f"<style>\n{root_vars}\n{_STATIC_CSS}{fixed_header_css}{custom}{extra}\n</style>"


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
    indices: list | None = None,
) -> str:
    """Return HTML for the page-menu column widget.

    Renders a nav list of all visible pages (system + free) sorted by global
    sort_order, excluding Home (the widget lives on the home page itself).

    Kept in sync with ``_render_navbar`` so the widget lists the same
    destinations the navbar does — Browse, Search, Indices (aggregate,
    only when at least one index is built), Bibliography, plus every
    free page.

    When *site_base_url* is empty (static mode) paths are relative to the site
    root (index.html lives there).  When set (dynamic/hybrid mode), absolute
    URLs rooted at *site_base_url* are used instead.
    """
    menu_items: list[tuple[int, str]] = []

    # System pages (Home is excluded: this widget is on index.html).
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
        elif pid == "indices":
            # Mirror the navbar: only surface the aggregate "Indices"
            # link when at least one index has actually been built —
            # otherwise the target page would render empty.
            has_built = any(idx.last_built_at for idx in (indices or []))
            if has_built:
                href = (
                    f"{site_base_url}/indices/"
                    if site_base_url
                    else "indices.html"
                )
                menu_items.append((so, f'<li><a href="{href}">Indices</a></li>'))
        elif pid == "bibliography":
            href = (
                f"{site_base_url}/bibliography"
                if site_base_url
                else "bibliography.html"
            )
            menu_items.append(
                (so, f'<li><a href="{href}">Bibliography</a></li>')
            )

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
            _build_page_menu_html(pages or [], nav_config, site_base_url, indices),
        )
        result = result.replace(
            _WIDGET_TAG_INDEX_LIST,
            _build_index_list_widget_html(indices, nav_config, site_base_url),
        )
        # Tiptap inserts <p></p> between consecutive block atoms. Collapse those
        # empty paragraphs between adjacent widget navs so the CSS adjacent-
        # sibling rule (nav + nav) fires correctly and the separator renders.
        result = re.sub(r"(</nav>)\s*(?:<p>\s*</p>\s*)+(<nav\b)", r"\1\2", result)
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
        "home":          {"id": "home",          "sort_order": 0, "is_hidden": False},
        "browse":        {"id": "browse",        "sort_order": 1, "is_hidden": False},
        "search":        {"id": "search",        "sort_order": 2, "is_hidden": False},
        "indices":       {"id": "indices",       "sort_order": 3, "is_hidden": False},
        "bibliography":  {"id": "bibliography",  "sort_order": 4, "is_hidden": False},
    }
    merged: dict[str, dict] = {}
    for page_id, default in _defaults.items():
        saved = next((p for p in nav_config if isinstance(p, dict) and p.get("id") == page_id), None)
        merged[page_id] = {**default, **(saved or {})}

    rest = sorted(
        [merged["browse"], merged["search"], merged["indices"], merged["bibliography"]],
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
        bibliography_href = f"{site_base_url}/bibliography"
    else:
        home_href = f"{path_prefix}index.html"
        browse_href = f"{path_prefix}browse.html"
        search_href = f"{path_prefix}search.html"
        bibliography_href = f"{path_prefix}bibliography.html"

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
        elif pid == "bibliography":
            nav_items.append((so, f'<a href="{bibliography_href}">Bibliography</a>'))

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


def _build_meta_tags(meta: dict, website_url: str | None = None) -> str:
    """Build HTML <meta> tag strings from a meta_config dict.

    Standard HTML meta tags and Dublin Core (DC.*) are emitted only for
    non-empty values.  The DC namespace <link> is prepended automatically
    when at least one DC field has a value.  Repeatable fields may be stored
    as either a plain string or a list of strings.

    When *website_url* is provided it is emitted as a DC.identifier tag with
    scheme="DCTERMS.URI":
        <meta name="DC.identifier" scheme="DCTERMS.URI" content="…">
    The DCTERMS schema link is added automatically alongside the DC link.
    """
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

    # website_url → DC.identifier with DCTERMS.URI scheme (canonical site URL)
    if website_url and website_url.strip():
        escaped = _html.escape(website_url.strip())
        dc_lines.append(
            f'  <meta name="DC.identifier" scheme="DCTERMS.URI" content="{escaped}">'
        )

    if dc_lines:
        lines.append('  <link rel="schema.DC" href="http://purl.org/dc/elements/1.1/" />')
        if website_url and website_url.strip():
            lines.append('  <link rel="schema.DCTERMS" href="http://purl.org/dc/terms/" />')
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
    # Patch <a href> links
    'function patch(a){'
    'var h=a.getAttribute("href");'
    'if(!h||/^(https?:|\\/\\/|mailto:|#)/.test(h)||h.indexOf("_preview=")!==-1)return;'
    'a.setAttribute("href",h+(h.indexOf("?")!==-1?"&":"?")+"_preview="+t);}'
    'document.querySelectorAll("a[href]").forEach(patch);'
    # Patch <form> elements: inject hidden _preview input so GET submissions carry the token
    'function patchForm(f){'
    'if(!f.querySelector("input[name=\\"_preview\\"]")){'
    'var inp=document.createElement("input");'
    'inp.type="hidden";inp.name="_preview";inp.value=t;'
    'f.appendChild(inp);}}'
    'document.querySelectorAll("form").forEach(patchForm);'
    # MutationObserver: patch newly inserted links and forms
    'new MutationObserver(function(ms){'
    'ms.forEach(function(m){'
    'm.addedNodes.forEach(function(n){'
    'if(n.querySelectorAll){'
    'n.querySelectorAll("a[href]").forEach(patch);'
    'n.querySelectorAll("form").forEach(patchForm);}'
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
    tei_valid_badge: str = "",
    meta_tags: str = "",
    custom_js: str | None = None,
    include_jquery: bool = False,
    website_slug: str | None = None,
    static_media_collected: set[str] | None = None,
    static_media_prefix: str = "media/",
    body_class: str = "",
) -> str:
    """Render the outer HTML shell around *content*.

    If ``website_slug`` is provided, ``media://filename`` references in
    the final HTML are rewritten. When ``static_media_collected`` is
    a set, STATIC mode is assumed and referenced filenames are added
    to it (for the builder to copy into the output tree).
    ``static_media_prefix`` controls the relative URL prefix in STATIC
    mode — ``"media/"`` for root-level files, ``"../media/"`` for
    pages under ``pages/`` or ``docs/``.

    Otherwise DYNAMIC mode: references become absolute API URLs, and
    the page location does not matter.
    """
    esc_site = _html.escape(site_title)
    esc_page = _html.escape(page_title)
    footer_extra = f'<span class="footer-publisher">{footer_note}</span> · ' if footer_note else ""
    if identifier_url:
        label = _identifier_label(identifier_url)
        esc_url = _html.escape(identifier_url)
        footer_extra += f'<a href="{esc_url}" class="footer-identifier" target="_blank" rel="noopener">{label}</a> · '
    if tei_valid_badge:
        # The badge HTML is trusted — built by _tei_valid_badge_html from
        # system-controlled data (a date string and a fixed template).
        footer_extra += f'{tei_valid_badge} · '
    meta_block = f"\n{meta_tags}" if meta_tags else ""
    breadcrumb_block = f"\n  {breadcrumb}" if breadcrumb else ""
    jquery_tag = (
        '<script src="https://code.jquery.com/jquery-3.7.1.min.js"'
        ' crossorigin="anonymous"></script>'
        if include_jquery else ""
    )
    # Custom JS is trusted Designer input; strip </script> to prevent tag break.
    custom_js_tag = (
        f"<script>\n{custom_js.replace('</script>', '')}\n</script>" if custom_js else ""
    )
    body_attr = f' class="{_html.escape(body_class)}"' if body_class else ""
    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc_page} — {esc_site}</title>{meta_block}
  {style}
</head>
<body{body_attr}>
  {navbar}{breadcrumb_block}
  <main>
    {content}
  </main>
  <footer>{footer_extra}Built with <a href="https://github.com/orazio-nelson/aracne2">Aracne2</a></footer>
  {_PREVIEW_PROPAGATOR_SCRIPT}
  {_HIGHLIGHT_SCRIPT}
  {jquery_tag}
  {custom_js_tag}
</body>
</html>"""

    if website_slug:
        from app.services import website_media as _wm

        mode = "static" if static_media_collected is not None else "dynamic"
        html_out = _wm.rewrite_media_refs(
            html_out,
            website_slug,
            mode=mode,
            collected=static_media_collected,
            static_prefix=static_media_prefix,
        )

    return html_out


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
    # XXE-hardened parser; eXist holds Editor-authored TEI and is
    # not a trust boundary on its own. See public_view.py.
    _safe_parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    xml_doc = etree.fromstring(xml_bytes, parser=_safe_parser)
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
            check_ssrf(url)
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
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

    *site_base_url*: when set (dynamic/hybrid mode), the column-widget
    hrefs use absolute paths; otherwise relative static paths.
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

    # ── Hero background + overlay ─────────────────────────────────────────
    # Both optional, both driven by ``theme_config``. The image is stored
    # as a ``media://filename`` pseudo-URL so the existing rewriter
    # translates it to a real URL at serve / build time.
    #
    # Where the CSS vars live depends on the home width mode:
    #
    # * ``standard`` / ``fullscreen`` → the vars are inline on the hero
    #   element, which then draws the background within its own box.
    # * ``cover`` → the vars are attached to ``<body.home-cover>`` via a
    #   small inline <style> block prepended to the content. The body
    #   paints the background under *all* page content (nav, hero,
    #   home-body, footer), producing the "book cover" effect — title
    #   and lead stack at their natural size with the image flowing
    #   behind and through the whole page.
    hero_bg = (theme.get("home_bg_image") or "").strip()
    overlay_rgba = _overlay_rgba(
        theme.get("home_overlay_color") or "#000000",
        theme.get("home_overlay_alpha"),
    )
    is_cover = (theme.get("home_width") or "standard") == "cover"

    style_block = ""
    hero_style_attr = ""
    hero_classes = "hero"
    if is_cover:
        parts: list[str] = []
        if hero_bg:
            parts.append(f"--hero-bg: url({hero_bg})")
        if overlay_rgba:
            parts.append(f"--hero-overlay: {overlay_rgba}")
        if parts:
            style_block = (
                f"<style>body.home-cover {{ {'; '.join(parts)} }}</style>"
            )
    else:
        hero_style_parts: list[str] = []
        if hero_bg:
            hero_style_parts.append(f"--hero-bg: url({hero_bg})")
        if overlay_rgba:
            hero_style_parts.append(f"--hero-overlay: {overlay_rgba}")
        hero_classes = "hero has-bg" if hero_bg else "hero"
        if hero_style_parts:
            hero_style_attr = f' style="{"; ".join(hero_style_parts)}"'

    # The hero no longer auto-renders a "Browse N documents" CTA — the
    # navbar + widget palette + free pages give the Designer enough
    # handles for that call-to-action, and the button was fighting the
    # typographic hierarchy of custom covers.
    hero = f"""{style_block}<div class="{hero_classes}"{hero_style_attr}>
  <h1>{title}</h1>
  {lead}
  {author_block}
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

    grid_template = _home_grid_template(layout, theme)
    grid_style = (
        f' style="grid-template-columns: {grid_template}"' if grid_template else ""
    )

    if layout == "two":
        # Unified two-column layout — content lives in col_left and
        # col_right; the slider controls the left-column percentage
        # and the right-column width follows from ``100 - N``.
        cols = (
            f'<div class="home-col">{left}</div>'
            f'<div class="home-col">{right}</div>'
        )
        css_class = "layout-two"
    elif layout == "two_left":
        # Legacy — older sites saved content in col_left + col_center.
        # Keep rendering these until the Designer re-saves the site,
        # at which point the frontend normaliser converts storage to
        # the new ``two`` shape.
        cols = (
            f'<div class="home-col">{left}</div>'
            f'<div class="home-col">{center}</div>'
        )
        css_class = "layout-two-left"
    elif layout == "two_right":
        # Legacy — same rationale as ``two_left``; content is in
        # col_center + col_right.
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
        grid = (
            f'<div class="home-body">'
            f'<div class="home-grid {css_class}"{grid_style}>{cols}</div>'
            f'</div>'
        )

    return hero + grid


# ── Home-page helpers ────────────────────────────────────────────────────────
#
# Kept next to _build_cover_content since the defaults they enshrine (old
# CSS fallbacks) are meaningful only in that context.


_HOME_DEFAULTS: dict[str, tuple[int, ...]] = {
    # layout → (left_pct, …) — historical defaults.
    # ``two`` is the current unified two-column layout; ``two_left``
    # and ``two_right`` are kept for backward-compatibility with sites
    # saved before the unification.
    "two": (30, 70),
    "two_left": (30, 70),
    "two_right": (70, 30),
    "three": (20, 60, 20),
}


def _clamp_pct(raw: object, default: int, low: int = 5, high: int = 95) -> int:
    try:
        v = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if v < low:
        return low
    if v > high:
        return high
    return v


def _home_grid_template(layout: str, theme: dict) -> str:
    """Resolve ``grid-template-columns`` from theme config per layout.

    Layouts refer to ``theme_config`` keys — ``home_cols_two_left``,
    ``home_cols_two_right``, ``home_cols_three_left``,
    ``home_cols_three_right`` — and fall back to the historical
    30/70, 70/30, 20/60/20 defaults when a key is unset or invalid.
    Returns the empty string for single-column and unknown layouts so
    the caller skips the inline style.
    """
    if layout in ("two", "two_left"):
        # ``two`` and legacy ``two_left`` both read the same slider
        # value (``home_cols_two_left`` — the left column %).
        left_default, _ = _HOME_DEFAULTS["two_left"]
        left = _clamp_pct(theme.get("home_cols_two_left"), left_default)
        return f"{left}% {100 - left}%"
    if layout == "two_right":
        # Legacy — ``home_cols_two_right`` stored the left (centre-
        # content) column width. The frontend normaliser migrates
        # this to ``home_cols_two_left`` on the next save.
        left_default, _ = _HOME_DEFAULTS["two_right"]
        left = _clamp_pct(theme.get("home_cols_two_right"), left_default)
        return f"{left}% {100 - left}%"
    if layout == "three":
        left_default, _center, right_default = _HOME_DEFAULTS["three"]
        left = _clamp_pct(theme.get("home_cols_three_left"), left_default, low=5, high=80)
        right = _clamp_pct(theme.get("home_cols_three_right"), right_default, low=5, high=80)
        # Guard: left + right must leave room for the centre column.
        if left + right > 90:
            scale = 90 / (left + right)
            left = max(5, int(left * scale))
            right = max(5, int(right * scale))
        center = 100 - left - right
        return f"{left}% {center}% {right}%"
    return ""


_HEX6_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_HEX3_RE = re.compile(r"^#?([0-9a-fA-F]{3})$")


def _overlay_rgba(color: str, alpha_raw: object) -> str:
    """Return an ``rgba(r,g,b,a)`` string or ``""`` if overlay disabled.

    Accepts 3- or 6-digit hex. Alpha is clamped to [0, 1]; values ≤ 0
    disable the overlay entirely (returns empty string).
    """
    color = (color or "").strip()
    hex_match = _HEX6_RE.match(color)
    if hex_match:
        h = hex_match.group(1)
    else:
        short = _HEX3_RE.match(color)
        if not short:
            return ""
        h = "".join(c * 2 for c in short.group(1))
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    try:
        a = float(alpha_raw) if alpha_raw is not None else 0.4
    except (TypeError, ValueError):
        a = 0.4
    if a <= 0:
        return ""
    if a > 1:
        a = 1.0
    # Format the alpha with two decimals — spares the inline style a
    # long float tail like ``0.30000000000000004``.
    return f"rgba({r},{g},{b},{a:.2f})"


def home_body_class(theme: dict | None) -> str:
    """Return the extra ``<body>`` class for a home-page render.

    Three values are honoured on ``theme_config.home_width``:
    ``"standard"`` (default — bounded 960px container, no extra class),
    ``"fullscreen"`` (``home-full`` — edge-to-edge hero, bounded body),
    and ``"cover"`` (``home-cover`` — hero fills the viewport below
    the navbar, content vertically centred, bg + overlay cover the
    whole visible area).
    """
    if not theme:
        return ""
    mode = theme.get("home_width") or "standard"
    if mode == "fullscreen":
        return "home-full"
    if mode == "cover":
        return "home-cover"
    return ""


_BROWSE_PAGE_SIZE = 20


def _build_browse_content(docs: list[dict], site_base_url: str = "") -> str:
    """Return the document list HTML for browse.html / dynamic browse page.

    Features:
    - Live text filter (title + author substring match, case-insensitive).
    - Client-side pagination (*_BROWSE_PAGE_SIZE* items per page).
    - Filter resets to page 1; pagination controls update dynamically.

    Each ``<li>`` carries a ``data-filter`` attribute (lowercased title +
    author) so the inline JS never needs a server round-trip.

    *site_base_url*: when set (dynamic/hybrid mode) doc links use absolute
    paths; otherwise relative static paths with .html extension.
    """
    count = len(docs)
    items = ""
    for doc in docs:
        filename = _html.escape(doc["filename"])
        label = _html.escape(doc.get("title") or doc["filename"])
        author = doc.get("author") or ""
        filter_text = _html.escape((label + " " + author + " " + doc["filename"]).lower())
        author_part = (
            f'<span class="doc-author">{_html.escape(author)}</span>'
            if author
            else ""
        )
        separator = " — " if author else ""
        meta_line = (
            f'<div class="doc-meta">'
            f'{author_part}'
            f'{separator}'
            f'<span class="doc-filename">{filename}</span>'
            f'</div>'
        )
        if site_base_url:
            href = f"{site_base_url}/docs/{filename}"
        else:
            href = f"docs/{filename}.html"
        sort_title = _html.escape(label.lower())
        sort_author = _html.escape(author.lower())
        sort_filename = _html.escape(doc["filename"].lower())
        items += (
            f'<li data-filter="{filter_text}"'
            f' data-title="{sort_title}"'
            f' data-author="{sort_author}"'
            f' data-filename="{sort_filename}">'
            f'<a href="{href}" class="doc-title">{label}</a>'
            f'{meta_line}</li>\n'
        )

    js = f"""\
(function(){{
var PAGE_SIZE={_BROWSE_PAGE_SIZE};
var inp=document.getElementById('browse-filter');
var cnt=document.getElementById('browse-count');
var no=document.getElementById('browse-no-results');
var pg=document.getElementById('browse-pagination');
var list=document.querySelector('.doc-list');
var allItems=Array.from(list.querySelectorAll('li'));
var filtered=allItems.slice();
var currentPage=1;
var sortKey='title';
var sortDir=1; // 1=asc, -1=desc

function applyFilterSort(){{
  var q=inp.value.trim().toLowerCase();
  filtered=q?allItems.filter(function(li){{return li.dataset.filter.indexOf(q)!==-1;}}):allItems.slice();
  filtered.sort(function(a,b){{
    var av=a.dataset[sortKey]||'';
    var bv=b.dataset[sortKey]||'';
    return av.localeCompare(bv,undefined,{{numeric:true,sensitivity:'base'}})*sortDir;
  }});
  currentPage=1;
  // re-append in sorted order so tab-order and DOM match
  filtered.forEach(function(li){{list.appendChild(li);}});
  render();
}}

function render(){{
  var total=filtered.length;
  var pages=Math.max(1,Math.ceil(total/PAGE_SIZE));
  if(currentPage>pages)currentPage=pages;
  var start=(currentPage-1)*PAGE_SIZE;
  var end=start+PAGE_SIZE;
  allItems.forEach(function(li){{li.style.display='none';}});
  filtered.forEach(function(li,i){{li.style.display=(i>=start&&i<end)?'':'none';}});
  // count label
  var q=inp.value.trim();
  if(q){{
    cnt.textContent=total+' of {count} document'+(({count})!==1?'s':'')+' matching \u201c'+q+'\u201d';
  }}else{{
    cnt.textContent=total+' document'+(total!==1?'s':'');
  }}
  no.style.display=(total===0&&q)?'':'none';
  // sort button arrows
  document.querySelectorAll('.browse-sort-btn').forEach(function(b){{
    var active=b.dataset.sort===sortKey;
    b.classList.toggle('sort-active',active);
    var arrow=b.querySelector('.sort-arrow');
    if(arrow)arrow.textContent=active?(sortDir===1?'\u25b4':'\u25be'):'';
  }});
  // pagination
  pg.innerHTML='';
  if(pages<=1)return;
  function btn(label,page,disabled,active){{
    var b=document.createElement('button');
    b.textContent=label;
    if(disabled)b.disabled=true;
    if(active)b.className='active';
    if(!disabled)b.addEventListener('click',function(){{currentPage=page;render();}});
    return b;
  }}
  pg.appendChild(btn('\u2039 Prev',currentPage-1,currentPage===1,false));
  var shown=[];
  for(var i=1;i<=pages;i++){{
    if(i===1||i===pages||Math.abs(i-currentPage)<=1)shown.push(i);
  }}
  var prev=0;
  shown.forEach(function(p){{
    if(prev&&p-prev>1){{
      var sp=document.createElement('span');
      sp.className='pg-ellipsis';sp.textContent='\u2026';pg.appendChild(sp);
    }}
    pg.appendChild(btn(String(p),p,false,p===currentPage));
    prev=p;
  }});
  pg.appendChild(btn('Next \u203a',currentPage+1,currentPage===pages,false));
}}

inp.addEventListener('input',function(){{applyFilterSort();}});

document.querySelectorAll('.browse-sort-btn').forEach(function(b){{
  b.addEventListener('click',function(){{
    var key=b.dataset.sort;
    if(sortKey===key){{sortDir=-sortDir;}}else{{sortKey=key;sortDir=1;}}
    applyFilterSort();
  }});
}});

applyFilterSort();
}})();"""

    return f"""<h1>Documents</h1>
<div class="browse-toolbar">
  <input type="search" id="browse-filter" class="browse-filter" style="margin-bottom:0" placeholder="Filter documents\u2026" autocomplete="off">
  <span class="browse-sort-label">Sort:</span>
  <button class="browse-sort-btn sort-active" data-sort="title">Title <span class="sort-arrow">\u25b4</span></button>
  <button class="browse-sort-btn" data-sort="author">Author <span class="sort-arrow"></span></button>
  <button class="browse-sort-btn" data-sort="filename">Filename <span class="sort-arrow"></span></button>
</div>
<p class="doc-count" id="browse-count" data-total="{count}">{count} document{'s' if count != 1 else ''}</p>
<p class="browse-no-results" id="browse-no-results" style="display:none">No documents match your filter.</p>
<ul class="doc-list">
{items}
</ul>
<div class="browse-pagination" id="browse-pagination"></div>
<script>{js}</script>"""


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


# Bare ``foo.xml`` token in a bibliography entry. Anchored on a
# non-word, non-dot, non-dash boundary so we only catch standalone
# filenames and not, e.g. ``my-archive.xml.zip``.
_BIBL_XML_FN_RE = re.compile(r"(?<![\w./\-])([A-Za-z0-9_][\w.\-]*\.xml)(?![\w./\-])")


def _linkify_bibl_filenames(
    text: str,
    available: set[str] | None,
    doc_url_for: Callable[[str], str] | None,
) -> str:
    """Wrap any whitelisted ``*.xml`` filename in *text* with an anchor tag.

    *text* is HTML-escaped already, so the inserted markup is safe.  When
    *available* is empty or *doc_url_for* is None the function is a no-op
    — we never link to a document the visitor cannot actually reach.
    """
    if not available or doc_url_for is None:
        return text

    def repl(m: re.Match[str]) -> str:
        fn = m.group(1)
        if fn not in available:
            return fn
        href = _html.escape(doc_url_for(fn), quote=True)
        return f'<a class="bibl-doc-link" href="{href}">{fn}</a>'

    return _BIBL_XML_FN_RE.sub(repl, text)


def _build_bibliography_content(
    content_xml: str | None,
    *,
    available_filenames: set[str] | None = None,
    doc_url_for: Callable[[str], str] | None = None,
) -> str:
    """Return the bibliography page HTML from a TEI <listBibl> XML string.

    Parses ``content_xml`` with defusedxml, extracts each ``<bibl>`` or
    ``<biblStruct>`` child, and renders a numbered list with descriptive
    CSS classes.  When ``content_xml`` is None, returns an empty-state
    message.

    When *available_filenames* and *doc_url_for* are provided, any bare
    ``foo.xml`` token in an entry that matches a real document on the
    site is converted into an anchor pointing at the document page
    (uses ``doc_url_for(filename)``).  Filenames not in the set are
    rendered as plain text — we never link to a document the visitor
    cannot actually reach.

    CSS classes used:
    - ``bibl-section``    — outer <section> wrapper
    - ``bibl-list``       — the <ul> element
    - ``bibl-entry``      — each <li>
    - ``bibl-number``     — the entry number span
    - ``bibl-text``       — the bibliographic text span
    - ``bibl-doc-link``   — anchor wrapping a linked filename
    - ``bibl-empty``      — <p> shown when no entries are available
    """
    import defusedxml.ElementTree as ET  # mandatory: no xml.etree.ElementTree

    if not content_xml:
        return '<section class="bibl-section"><p class="bibl-empty">No bibliography available.</p></section>'

    tei_ns = "http://www.tei-c.org/ns/1.0"
    entries: list[str] = []
    try:
        root = ET.fromstring(content_xml.encode())
        for tag in ("bibl", "biblStruct"):
            # Try namespaced elements first; fall back to no-namespace.
            nodes = root.findall(f".//{{{tei_ns}}}{tag}")
            if not nodes:
                nodes = root.findall(f".//{tag}")
            for node in nodes:
                text = " ".join("".join(node.itertext()).split()).strip()
                if text:
                    escaped = _html.escape(text)
                    entries.append(
                        _linkify_bibl_filenames(escaped, available_filenames, doc_url_for)
                    )
    except Exception:
        return '<section class="bibl-section"><p class="bibl-empty">Could not render bibliography.</p></section>'

    if not entries:
        return '<section class="bibl-section"><p class="bibl-empty">No bibliography entries found.</p></section>'

    items = "".join(
        f'<li class="bibl-entry">'
        f'<span class="bibl-number">{i + 1}.</span>'
        f'<span class="bibl-text">{text}</span>'
        f'</li>\n'
        for i, text in enumerate(entries)
    )
    return (
        f'<section class="bibl-section">'
        f'<ul class="bibl-list">\n{items}</ul>'
        f'</section>'
    )


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

def _inline_media_images(html: str, col_slug: str) -> str:
    """Replace media API ``src`` URLs with inline base64 data URIs.

    The preview iframe cannot send Bearer auth headers for ``<img>`` requests,
    so images would appear broken.  Reading from the filesystem and inlining
    them as data URIs is safe for a single-document admin preview.
    """
    import base64
    import mimetypes

    media_root = settings.documents_media_root / col_slug

    def _replace(match: re.Match[str]) -> str:
        doc_fn = match.group(1)   # e.g. "ara2.1.xml"
        img_fn = match.group(2)   # e.g. "screenshot.png"
        img_path = (media_root / doc_fn / img_fn).resolve()
        # Containment check — must stay inside documents_media_root.
        try:
            img_path.relative_to(settings.documents_media_root.resolve())
        except ValueError:
            return match.group(0)
        if not img_path.is_file():
            return match.group(0)
        mime = mimetypes.guess_type(str(img_path))[0] or "image/jpeg"
        data = base64.b64encode(img_path.read_bytes()).decode()
        return f'src="data:{mime};base64,{data}"'

    prefix = f"/api/v1/collections/{col_slug}/documents/"
    pattern = r'src="' + re.escape(prefix) + r'([^/]+)/media/([^"]+)"'
    return re.sub(pattern, _replace, html)


async def preview_document(
    db: AsyncSession,
    slug: str,
    filename: str,
    xslt_config_override: dict | None = None,
) -> str:
    """Apply XSLT to a single document and return a full preview HTML page.

    Used by the admin Document tab to preview rendering before a full build.
    If *xslt_config_override* is provided, it takes precedence over the
    website's saved xslt_config (allows previewing unsaved stylesheet changes).

    Images are inlined as base64 data URIs so they render without auth headers
    inside the sandboxed preview iframe.
    Image-rendering CSS overrides from ``image_rendering`` config are applied.
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

    # Inject facsimile gallery if enabled in image_rendering config.
    ir_cfg: dict = config.get("image_rendering") or {}
    if ir_cfg.get("enabled") and ir_cfg.get("facsimile_gallery"):
        doc_body = _inject_facsimile_gallery(doc_body, xml_bytes)

    # Inline media images as data URIs (preview iframe has no Bearer auth).
    doc_body = _inline_media_images(doc_body, col.slug)

    # Build image-rendering CSS overrides so the preview matches the static site.
    ir_css = _build_image_rendering_css(ir_cfg)
    ir_fig_layout = (ir_cfg.get("figure") or {}).get("layout", "inline")
    ir_pb_layout  = (ir_cfg.get("pb") or {}).get("layout", "inline")
    ir_modal  = bool(ir_cfg.get("enabled")) and (
        ir_fig_layout == "modal" or ir_pb_layout == "modal"
        or bool(ir_cfg.get("facsimile_gallery"))
        or ir_pb_layout == "one-to-one"  # OTO makes all figures modal-clickable
    )
    ir_column = bool(ir_cfg.get("enabled")) and (
        ir_fig_layout in ("column-left", "column-right")
        or ir_pb_layout in ("column-left", "column-right")
    )
    ir_oto = bool(ir_cfg.get("enabled")) and ir_pb_layout == "one-to-one"
    # Build note-rendering CSS/JS overrides.
    nr_cfg: dict = config.get("note_rendering") or {}
    nr_css: str = _build_note_rendering_css(nr_cfg)
    nr_js:  str = _build_note_rendering_js(nr_cfg)
    combined_css = "\n".join(s for s in (ir_css, nr_css) if s)
    ir_style = f"<style>{combined_css}</style>\n" if combined_css else ""
    extra_scripts = ""
    if ir_modal:
        extra_scripts += f"<script>{_IMAGE_MODAL_JS}</script>\n"
    if ir_column:
        extra_scripts += f"<script>{_build_image_column_js(ir_cfg)}</script>\n"
    if ir_oto:
        extra_scripts += f"<script>{_build_one_to_one_js(ir_cfg)}</script>\n"
    if nr_js:
        extra_scripts += f"<script>{nr_js}</script>\n"

    # Column and OTO previews need a <main> wrapper so JS can find .tei-body's parent.
    body_content = (
        f'<main><div class="tei-body">{doc_body}</div></main>'
        if ir_column or ir_oto
        else f'<div class="tei-body">{doc_body}</div>'
    )

    return (
        "<!DOCTYPE html><html><head>"
        "<meta charset='UTF-8'>"
        "<style>body{font-family:Georgia,'Times New Roman',serif;font-size:1rem;"
        "line-height:1.85;color:#1a1a1a;max-width:780px;margin:2rem auto;"
        "padding:0 1.25rem;background:#fff;}"
        "figure{margin:1.5rem auto;max-width:100%;text-align:center;}"
        "figure img{max-width:100%;height:auto;display:block;margin:0 auto;}"
        "figure.tei-pb-facsimile{border:1px solid #e5e7eb;border-radius:3px;padding:.5rem;background:#fafafa;}"
        "</style>"
        f"{ir_style}"
        f"</head><body>{body_content}"
        f"{extra_scripts}"
        "</body></html>"
    )


# ── Dynamic / Hybrid rendering ────────────────────────────────────────────────

def _kwic_highlight(text: str, q: str) -> str:
    """HTML-escape *text* and wrap query-term occurrences in ``<mark>``.

    Each whitespace-separated token in *q* is highlighted independently using
    a single case-insensitive alternation regex.  The input is escaped before
    the substitution so no existing markup can interfere.
    """
    escaped = _html.escape(text)
    if not q or not escaped:
        return escaped
    terms = [t for t in re.split(r"\s+", q.strip()) if t]
    if not terms:
        return escaped
    pattern = re.compile(
        "(" + "|".join(re.escape(_html.escape(t)) for t in terms) + ")",
        re.IGNORECASE,
    )
    return pattern.sub(r"<mark>\1</mark>", escaped)


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
        f'<form action="{esc_action}" method="get" style="display:flex;gap:.5rem;flex:1">'
        f'<input type="search" name="q" value="{esc_q}"'
        ' placeholder="Search documents\u2026" autocomplete="off" autofocus>'
        '<button type="submit" class="search-submit">Search</button>'
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
        kwic_html = _kwic_highlight(hit.get("kwic") or "", q)
        doc_href = _html.escape(f"{site_base_url}/docs/{hit['filename']}{hl_param}")
        items += (
            '<div class="search-hit">'
            f'<a href="{doc_href}">{filename}</a>'
            + (f'<div class="hit-kwic">{kwic_html}</div>' if kwic_html else "")
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
    base = f"/sites/{website.slug}"
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
    tei_valid_badge = await _tei_valid_badge_html(db, col)
    html = _render_page(
        site_title=website.title,
        page_title=website.title,
        content=content,
        style=_style_block(theme, website.custom_css),
        navbar=navbar,
        footer_note=footer_note,
        identifier_url=identifier_url,
        tei_valid_badge=tei_valid_badge,
        body_class=home_body_class(theme),
        meta_tags=_build_meta_tags(website.meta_config or {}, website_url=website.website_url),
        custom_js=website.custom_js,
        include_jquery=website.include_jquery,
        website_slug=website.slug,
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
    base = f"/sites/{website.slug}"
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
    tei_valid_badge = await _tei_valid_badge_html(db, col)
    html = _render_page(
        site_title=website.title,
        page_title="Browse",
        content=_build_browse_content(doc_infos, site_base_url=base),
        style=_style_block(theme, website.custom_css),
        navbar=navbar,
        breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, "Browse")]),
        footer_note=footer_note,
        identifier_url=identifier_url,
        tei_valid_badge=tei_valid_badge,
        meta_tags=_build_meta_tags(website.meta_config or {}, website_url=website.website_url),
        custom_js=website.custom_js,
        include_jquery=website.include_jquery,
        website_slug=website.slug,
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

    # Resolve the linked collection once, up front — every downstream
    # helper (search XQuery, footer, TEI-valid badge) needs it and the
    # original code lazily resolved ``col`` only inside the ``if q``
    # branch, which raised UnboundLocalError when the search page was
    # requested with an empty query.
    col: Collection | None = (
        await db.get(Collection, website.collection_id)
        if website.collection_id is not None
        else None
    )

    hits: list[dict] = []
    if q and col is not None:
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
    base = f"/sites/{website.slug}"
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
    tei_valid_badge = await _tei_valid_badge_html(db, col)
    html = _render_page(
        site_title=website.title,
        page_title="Search",
        content=_build_dynamic_search_content(hits, q, base),
        style=_style_block(theme, website.custom_css),
        navbar=navbar,
        breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, "Search")]),
        footer_note=footer_note,
        identifier_url=identifier_url,
        tei_valid_badge=tei_valid_badge,
        meta_tags=_build_meta_tags(website.meta_config or {}, website_url=website.website_url),
        custom_js=website.custom_js,
        include_jquery=website.include_jquery,
        website_slug=website.slug,
    )
    if q:
        _set_cached_page(website.slug, path_key, html)
    return html


async def render_dynamic_bibliography(db: AsyncSession, website: Website) -> str:
    """Render the bibliography page for a DYNAMIC or HYBRID website.

    Fetches the public bibliography of the linked collection from PostgreSQL
    and renders it as a numbered HTML list.  Results are cached with the
    website's effective TTL.
    """
    from app.models.collection_bibliography import CollectionBibliography

    ttl = _get_cache_ttl(website)
    cached = _get_cached_page(website.slug, "bibliography", ttl)
    if cached is not None:
        return cached

    theme = website.theme_config or {}
    base = f"/sites/{website.slug}"
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

    content_xml: str | None = None
    if website.collection_id is not None:
        row = await db.scalar(
            select(CollectionBibliography).where(
                CollectionBibliography.collection_id == website.collection_id,
                CollectionBibliography.is_public.is_(True),
            )
        )
        if row is not None:
            content_xml = row.content

    col: Collection | None = (
        await db.get(Collection, website.collection_id)
        if website.collection_id else None
    )
    footer_note, identifier_url = _footer_parts(col)
    tei_valid_badge = await _tei_valid_badge_html(db, col)

    # List the collection's documents so we can linkify bibliography
    # entries that mention an existing TEI filename. Failures here
    # only mean no links are added — the bibliography itself is
    # unaffected.
    doc_filenames: set[str] = set()
    if col is not None:
        try:
            doc_filenames = set(await existdb_client.list_collection(col.slug))
        except Exception:
            doc_filenames = set()

    html = _render_page(
        site_title=website.title,
        page_title="Bibliography",
        content=_build_bibliography_content(
            content_xml,
            available_filenames=doc_filenames,
            doc_url_for=lambda fn: f"{base}/docs/{fn}",
        ),
        style=_style_block(theme, website.custom_css),
        navbar=navbar,
        breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, "Bibliography")]),
        footer_note=footer_note,
        identifier_url=identifier_url,
        tei_valid_badge=tei_valid_badge,
        meta_tags=_build_meta_tags(website.meta_config or {}, website_url=website.website_url),
        custom_js=website.custom_js,
        include_jquery=website.include_jquery,
        website_slug=website.slug,
    )
    _set_cached_page(website.slug, "bibliography", html)
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
    base = f"/sites/{website.slug}"
    visible_pages = [p for p in website.pages if not p.is_hidden]
    hide_header: bool = bool(theme.get("hide_header", False))

    aracne_nav = _parse_aracne_nav(website.nav_config or [])
    browse_hidden = bool(
        next((ap for ap in aracne_nav if ap["id"] == "browse"), {}).get("is_hidden", False)
    )

    # Image-rendering and note-rendering CSS + JS overrides (same wiring
    # the STATIC builder applies to its on-disk doc pages). Without
    # this block the tooltip / side-frame note modes rendered as
    # unstyled end-of-text lists on DYNAMIC / HYBRID doc pages — and
    # inline facsimile / column-layout image modes went back to the
    # default XSLT output. Keep in sync with ``_build_static_site``.
    _xslt_cfg: dict = website.xslt_config or {}
    _ir_cfg: dict = _xslt_cfg.get("image_rendering") or {}
    _ir_enabled: bool = bool(_ir_cfg.get("enabled"))
    _ir_css: str = _build_image_rendering_css(_ir_cfg)
    _ir_fig_layout = (_ir_cfg.get("figure", {}) or {}).get("layout", "inline")
    _ir_pb_layout = (_ir_cfg.get("pb", {}) or {}).get("layout", "inline")
    _ir_modal: bool = _ir_enabled and (
        _ir_fig_layout == "modal"
        or _ir_pb_layout == "modal"
        or bool(_ir_cfg.get("facsimile_gallery"))
        or _ir_pb_layout == "one-to-one"
    )
    _ir_column: bool = _ir_enabled and (
        _ir_fig_layout in ("column-left", "column-right")
        or _ir_pb_layout in ("column-left", "column-right")
    )
    _ir_oto: bool = _ir_enabled and _ir_pb_layout == "one-to-one"
    _nr_cfg: dict = _xslt_cfg.get("note_rendering") or {}
    _nr_css: str = _build_note_rendering_css(_nr_cfg)
    _nr_js: str = _build_note_rendering_js(_nr_cfg)
    _eh_cfg: dict = _xslt_cfg.get("entity_hover") or {}
    _eh_js: str = _build_entity_hover_js(_eh_cfg)
    _doc_extra_css: str | None = (_ir_css + "\n" + _nr_css).strip() or None

    custom_js = website.custom_js
    if _ir_modal:
        custom_js = (custom_js or "") + "\n" + _IMAGE_MODAL_JS
    if _ir_column:
        custom_js = (custom_js or "") + "\n" + _build_image_column_js(_ir_cfg)
    if _ir_oto:
        custom_js = (custom_js or "") + "\n" + _build_one_to_one_js(_ir_cfg)
    if _nr_js:
        custom_js = (custom_js or "") + "\n" + _nr_js
    if _eh_js:
        custom_js = (custom_js or "") + "\n" + _eh_js

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
    tei_valid_badge = await _tei_valid_badge_html(db, col)
    actions = _doc_actions_toolbar(website.slug, filename)
    html = _render_page(
        site_title=website.title,
        page_title=label,
        content=f'{actions}<div class="tei-body">{doc_body}</div>',
        style=_style_block(theme, website.custom_css, _doc_extra_css),
        navbar=navbar,
        breadcrumb=_render_breadcrumb(crumbs),
        footer_note=footer_note,
        identifier_url=identifier_url,
        tei_valid_badge=tei_valid_badge,
        custom_js=custom_js,
        include_jquery=website.include_jquery,
        website_slug=website.slug,
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
    base = f"/sites/{website.slug}"
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
    tei_valid_badge = await _tei_valid_badge_html(db, col)
    content_html = _md_to_html(page.content_md or "")
    html = _render_page(
        site_title=website.title,
        page_title=page.title,
        content=f"<h1>{_html.escape(page.title)}</h1>\n{content_html}",
        style=_style_block(theme, website.custom_css),
        navbar=navbar,
        breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, page.title)]),
        footer_note=footer_note,
        identifier_url=identifier_url,
        tei_valid_badge=tei_valid_badge,
        custom_js=website.custom_js,
        include_jquery=website.include_jquery,
        website_slug=website.slug,
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


async def _tei_valid_badge_html(
    db: AsyncSession, col: Collection | None
) -> str:
    """Return footer-badge HTML when the collection has a green validation.

    Empty string means "no badge" — the caller can unconditionally
    inline the result. Gated by the global setting
    ``public_tei_valid_badge_enabled`` (default true) so a deployment
    that prefers not to make public validation claims can hide the
    badge on every site at once.

    "Green" here means the latest completed full-collection validation
    run has ``status == 'done'`` AND ``error_count == 0``. Runs that
    are still in progress (``pending`` / ``running``), were cancelled,
    or ended with errors never produce a badge. The date shown in the
    tooltip is the ``completed_at`` timestamp — the badge asserts "was
    valid on that day", not "is always valid right now". Editors can
    re-run the validation any time from the Collection detail page to
    refresh the stamp.
    """
    if col is None:
        return ""
    # Global kill switch — read every time so toggling the setting
    # takes effect at the next page render (DYNAMIC) or next rebuild
    # (STATIC / HYBRID).
    row = await db.get(SystemSetting, "public_tei_valid_badge_enabled")
    if row is None or (row.value or "").strip().lower() != "true":
        return ""

    stmt = (
        select(CollectionValidationRun)
        .where(
            CollectionValidationRun.collection_id == col.id,
            CollectionValidationRun.status == ValidationRunStatus.done,
        )
        .order_by(CollectionValidationRun.completed_at.desc())
        .limit(1)
    )
    run = await db.scalar(stmt)
    if run is None or run.error_count != 0:
        return ""

    when = run.completed_at or run.started_at
    date_str = when.date().isoformat() if when else "unknown"
    # Inline SVG so the badge renders even for sites hosted on domains
    # that block external icon CDNs.
    svg = (
        '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
        '<path d="M12 2 4 5v6c0 5 3.5 9.4 8 11 4.5-1.6 8-6 8-11V5l-8-3Zm-1 14-4-4 1.4-1.4L11 13.2l4.6-4.6L17 10l-6 6Z"/>'
        "</svg>"
    )
    return (
        '<a id="tei-valid-badge" class="footer-tei-valid" '
        'href="https://tei-c.org/release/doc/tei-p5-doc/en/html/" '
        'target="_blank" rel="noopener" '
        f'title="Validated on {_html.escape(date_str)}">'
        f"{svg}TEI valid</a>"
    )


# ── Maintenance mode ──────────────────────────────────────────────────────────


async def is_website_in_maintenance(
    db: AsyncSession, website: Website
) -> bool:
    """True when the website should render its maintenance banner instead
    of normal content.

    Triggers when **both** conditions hold:
      1. ``website.maintenance_on_unpublish`` is True (the operator wants
         the banner behaviour for this site — STATIC defaults to False so
         releases can outlive transient unpublishes).
      2. The linked collection is missing, soft-deleted, or not in the
         ``published`` + ``is_public=True`` state.

    When the site has no linked collection (``collection_id is None``),
    the flag has nothing to gate on and the function returns False.
    """
    if not website.maintenance_on_unpublish:
        return False
    if website.collection_id is None:
        return False
    col = await db.get(Collection, website.collection_id)
    if col is None:
        return True
    is_live = (
        col.status == CollectionStatus.published
        and bool(col.is_public)
    )
    return not is_live


def build_maintenance_html(
    website: Website,
    *,
    admin_email: str,
    default_message: str | None = None,
) -> str:
    """Render the 503 maintenance banner HTML for a given website.

    Uses the website's own theme (logo, colour palette, custom CSS) so
    the page visually matches the rest of the site — the banner is a
    state, not a redirect to a generic platform page.

    Fallbacks:
      - ``maintenance_message`` on the website → first;
      - ``default_message`` argument (i18n-resolved by the caller) → second;
      - a hard-coded English phrase → last-resort.
    """
    theme = website.theme_config or {}
    effective_email = (website.contact_email or "").strip() or admin_email
    message = (
        (website.maintenance_message or "").strip()
        or (default_message or "").strip()
        or "This edition is temporarily unavailable. Please check back soon."
    )
    # Show a site logo if the theme carries one; otherwise fall back to
    # the platform mark so the banner is never blank.
    site_logo_url = theme.get("logo_url") or ""
    platform_logo_url = "/aracne-icons/lockup/aracne-lockup-vertical-512.png"

    # Escape the message — it is Designer-authored but we still do not
    # want newlines or angle brackets leaking raw into the template.
    from html import escape

    msg_html = escape(message).replace("\n", "<br/>")
    email_html = escape(effective_email)

    body_html = f"""
      <main class="maint-wrap">
        <div class="maint-card">
          <div class="maint-logos">
            {f'<img src="{escape(site_logo_url)}" alt="" class="maint-site-logo"/>' if site_logo_url else ""}
            <img src="{platform_logo_url}" alt="Aracne2" class="maint-platform-logo"/>
          </div>
          <h1 class="maint-title">{escape(website.title)}</h1>
          <p class="maint-message">{msg_html}</p>
          <p class="maint-contact">
            <a href="mailto:{email_html}">{email_html}</a>
          </p>
        </div>
      </main>
    """.strip()

    return _render_page(
        site_title=website.title,
        page_title=f"{website.title} — Maintenance",
        content=body_html,
        style=_style_block(theme, website.custom_css, extra_css=_MAINT_CSS),
        navbar="",
        meta_tags='<meta name="robots" content="noindex, nofollow"/>',
        custom_js=None,
    )


_MAINT_CSS = """
.maint-wrap {
  min-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
}
.maint-card {
  max-width: 520px;
  text-align: center;
}
.maint-logos {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  margin-bottom: 28px;
}
.maint-site-logo { max-height: 72px; width: auto; }
.maint-platform-logo { max-height: 256px; width: auto; opacity: 0.5; }
.maint-title {
  font-size: 1.6rem;
  font-weight: 600;
  margin-bottom: 14px;
}
.maint-message {
  font-size: 1rem;
  line-height: 1.5;
  color: #374151;
  margin-bottom: 24px;
}
.maint-contact {
  font-size: 0.95rem;
  color: #6b7280;
}
.maint-contact a {
  color: #4f46e5;
  text-decoration: none;
}
.maint-contact a:hover { text-decoration: underline; }
"""


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

    # Per-mode default for maintenance_on_unpublish:
    #   STATIC  → False (the site is a "release" that may intentionally
    #                    outlive a transient collection unpublish);
    #   DYNAMIC → True  (dynamic rendering depends on the collection
    #                    being published; the banner is the humane
    #                    fallback over a raw 404);
    #   HYBRID  → True  (same reason, for the dynamic half).
    if data.maintenance_on_unpublish is None:
        maint_default = data.rendering_mode != RenderingMode.STATIC
    else:
        maint_default = data.maintenance_on_unpublish

    website = Website(
        slug=data.slug,
        title=data.title,
        description=data.description,
        collection_id=data.collection_id,
        rendering_mode=data.rendering_mode,
        website_url=data.website_url,
        theme_config=data.theme_config,
        meta_config=data.meta_config,
        nav_config=data.nav_config,
        xslt_schema_id=data.xslt_schema_id,
        is_published=data.is_published,
        show_in_public_home=data.show_in_public_home,
        maintenance_on_unpublish=maint_default,
        maintenance_message=data.maintenance_message,
        contact_email=data.contact_email,
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
    await db.refresh(website, attribute_names=["pages", "indices"])
    # Any metadata or XSLT change must invalidate the rendered-page and XSLT caches
    # immediately so dynamic/hybrid sites do not serve stale HTML.
    invalidate_cache(slug)
    return website


async def delete_website(db: AsyncSession, slug: str) -> None:
    website = await _get_website(db, slug)
    # Clean up generated static files if they exist.
    site_dir = settings.websites_root / slug
    if not site_dir.resolve().is_relative_to(settings.websites_root.resolve()):
        raise DomainValidationError(code="INVALID_SLUG", message="Slug resolves outside the allowed directory")
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
    style = _style_block(theme, website.custom_css)
    site_base_url = f"/sites/{website.slug}"

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
        meta_tags=_build_meta_tags(website.meta_config or {}, website_url=website.website_url),
        custom_js=website.custom_js,
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
    ``/sites/my-site``).  For static builds, leave it empty and set
    ``path_prefix`` to the relative path from the current page to the site root
    (empty string for root-level pages, ``../`` for subdirectory pages).
    """
    built = [idx for idx in (website.indices or []) if idx.cached_data is not None]

    theme = website.theme_config or {}
    style = _style_block(theme, website.custom_css)

    effective_base = site_base_url or f"/sites/{website.slug}"

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
            meta_tags=_build_meta_tags(website.meta_config or {}, website_url=website.website_url),
            custom_js=website.custom_js,
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
        meta_tags=_build_meta_tags(website.meta_config or {}, website_url=website.website_url),
        custom_js=website.custom_js,
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
    if not site_dir.resolve().is_relative_to(settings.websites_root.resolve()):
        raise DomainValidationError(code="INVALID_SLUG", message="Slug resolves outside the allowed directory")
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "docs").mkdir(exist_ok=True)
    (site_dir / "pages").mkdir(exist_ok=True)

    # Per-website managed-media references collected across every page
    # rendered in this build. At the end we copy just these files into
    # ``site_dir/media/`` so the static tree stays self-contained
    # without dumping the whole media folder into the output.
    referenced_media: set[str] = set()

    # ── Image rendering configuration ─────────────────────────────────────
    _ir_cfg: dict = (website.xslt_config or {}).get("image_rendering") or {}
    _ir_css: str = _build_image_rendering_css(_ir_cfg)
    _ir_enabled: bool = bool(_ir_cfg.get("enabled"))
    _ir_gallery: bool = _ir_enabled and bool(_ir_cfg.get("facsimile_gallery"))
    _ir_fig_layout  = (_ir_cfg.get("figure", {}) or {}).get("layout", "inline")
    _ir_pb_layout   = (_ir_cfg.get("pb", {}) or {}).get("layout", "inline")
    _ir_modal: bool = _ir_enabled and (
        _ir_fig_layout == "modal" or _ir_pb_layout == "modal"
        or _ir_gallery
        or _ir_pb_layout == "one-to-one"  # OTO makes all figures modal-clickable
    )
    _ir_column: bool = _ir_enabled and (
        _ir_fig_layout in ("column-left", "column-right")
        or _ir_pb_layout in ("column-left", "column-right")
    )
    _ir_oto: bool = _ir_enabled and _ir_pb_layout == "one-to-one"
    # Note rendering configuration.
    _nr_cfg: dict = (website.xslt_config or {}).get("note_rendering") or {}
    _nr_css: str = _build_note_rendering_css(_nr_cfg)
    _nr_js:  str = _build_note_rendering_js(_nr_cfg)
    # Entity-hover (Wikidata preview) configuration.
    _eh_cfg: dict = (website.xslt_config or {}).get("entity_hover") or {}
    _eh_js: str = _build_entity_hover_js(_eh_cfg)
    # Combine image and note rendering CSS for doc pages.
    _doc_extra_css: str | None = (_ir_css + "\n" + _nr_css).strip() or None
    # Append image-rendering CSS to the per-site style block (doc pages only;
    # non-doc pages share the same style but show no TEI content).
    doc_style = _style_block(theme, website.custom_css, _doc_extra_css)
    style = _style_block(theme, website.custom_css)
    # Append modal, column, OTO, note-rendering, and entity-hover JS to the
    # site's custom JS when the matching feature is active.
    # base_custom_js is the un-enhanced value used for non-document pages (e.g. bibliography)
    # so that image/note rendering scripts do not appear on pages with no documents.
    base_custom_js = website.custom_js
    custom_js = base_custom_js
    if _ir_modal:
        custom_js = (custom_js or "") + "\n" + _IMAGE_MODAL_JS
    if _ir_column:
        custom_js = (custom_js or "") + "\n" + _build_image_column_js(_ir_cfg)
    if _ir_oto:
        custom_js = (custom_js or "") + "\n" + _build_one_to_one_js(_ir_cfg)
    if _nr_js:
        custom_js = (custom_js or "") + "\n" + _nr_js
    if _eh_js:
        custom_js = (custom_js or "") + "\n" + _eh_js
    include_jquery = website.include_jquery

    # Only visible free pages appear in the navigation.
    visible_pages = [p for p in website.pages if not p.is_hidden]

    # Resolve Aracne system-page visibility from nav_config.
    aracne_nav = _parse_aracne_nav(website.nav_config or [])
    _nav_map = {ap["id"]: ap for ap in aracne_nav}
    browse_hidden: bool = bool(_nav_map.get("browse", {}).get("is_hidden", False))
    search_hidden: bool = bool(_nav_map.get("search", {}).get("is_hidden", False))
    indices_hidden: bool = bool(_nav_map.get("indices", {}).get("is_hidden", False))
    bibliography_hidden: bool = bool(_nav_map.get("bibliography", {}).get("is_hidden", False))

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
    meta_tags: str = _build_meta_tags(website.meta_config or {}, website_url=website.website_url)

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
    tei_valid_badge = await _tei_valid_badge_html(db, col)

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
        tei_valid_badge=tei_valid_badge,
        meta_tags=meta_tags,
        custom_js=custom_js,
        include_jquery=include_jquery,
        website_slug=slug,
        static_media_collected=referenced_media,
        body_class=home_body_class(theme),
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
            tei_valid_badge=tei_valid_badge,
            meta_tags=meta_tags,
            custom_js=custom_js,
            include_jquery=include_jquery,
            website_slug=slug,
            static_media_collected=referenced_media,
        )
        (site_dir / "browse.html").write_text(browse_html, encoding="utf-8")

    # ── bibliography.html — public bibliography (skipped when hidden) ────────
    if not bibliography_hidden:
        from app.models.collection_bibliography import CollectionBibliography as _CB
        bib_xml: str | None = None
        if website.collection_id is not None:
            bib_row = await db.scalar(
                select(_CB).where(
                    _CB.collection_id == website.collection_id,
                    _CB.is_public.is_(True),
                )
            )
            if bib_row is not None:
                bib_xml = bib_row.content
        static_doc_set = {d["filename"] for d in doc_infos}
        bibliography_html = _render_page(
            site_title=website.title,
            page_title="Bibliography",
            content=_build_bibliography_content(
                bib_xml,
                available_filenames=static_doc_set,
                doc_url_for=lambda fn: f"docs/{fn}.html",
            ),
            style=style,
            navbar=navbar(),
            breadcrumb=_render_breadcrumb([("index.html", "Home"), (None, "Bibliography")]),
            footer_note=footer_note,
            identifier_url=identifier_url,
            tei_valid_badge=tei_valid_badge,
            meta_tags=meta_tags,
            custom_js=base_custom_js,
            include_jquery=include_jquery,
            website_slug=slug,
            static_media_collected=referenced_media,
        )
        (site_dir / "bibliography.html").write_text(bibliography_html, encoding="utf-8")

    # ── docs/{filename}.html — individual documents ────────────────────────
    # doc_bodies accumulates plain text for the full-text search index.
    doc_bodies: dict[str, str] = {}

    # API URL prefix for media files of this collection.
    # Stored in <graphic url="…"> by the editor.  In the static site these
    # files are served from the copied media/ directory, so the prefix is
    # replaced with a relative path when rewriting HTML.
    _media_api_prefix = f"/api/v1/collections/{col.slug if col else ''}/documents/"

    if col is not None:
        # ── Copy media files for all documents ────────────────────────────
        # Source: <documents_media_root>/<col_slug>/
        # Destination: <site_dir>/media/  (mirrors the same directory tree)
        col_media_src = settings.documents_media_root / col.slug
        col_media_dst = site_dir / "media"
        if col_media_src.exists():
            try:
                if col_media_dst.exists():
                    shutil.rmtree(col_media_dst)
                shutil.copytree(col_media_src, col_media_dst)
            except Exception as exc:
                logger.warning(
                    "website_build_media_copy_failed", slug=slug, error=str(exc)
                )

        for doc_info in doc_infos:
            filename = doc_info["filename"]
            xml_bytes_doc: bytes = b""
            try:
                xml_bytes_doc = await existdb_client.get_document(col.slug, filename)
                doc_body = await asyncio.to_thread(xslt_transform, xml_bytes_doc)
                doc_bodies[filename] = _extract_plain_text(xml_bytes_doc)
            except Exception as exc:
                logger.warning(
                    "website_build_doc_failed", slug=slug, filename=filename, error=str(exc)
                )
                doc_body = f"<p>Could not render document: {_html.escape(str(exc))}</p>"

            # Inject facsimile gallery at the top of the document body when
            # enabled.  The gallery contains API URLs that the URL-rewrite step
            # below converts to relative paths, so order matters.
            if _ir_gallery and xml_bytes_doc:
                doc_body = _inject_facsimile_gallery(doc_body, xml_bytes_doc)

            # Rewrite API media URLs to relative paths.
            # Pattern: /api/v1/collections/{slug}/documents/{doc_filename}/media/{file}
            # becomes: ../media/{doc_filename}/{file}
            # The generated HTML lives in docs/ so one ../ is needed.
            doc_body = re.sub(
                r'src="' + re.escape(_media_api_prefix) + r'([^/]+)/media/([^"]+)"',
                r'src="../media/\1/\2"',
                doc_body,
            )

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
            doc_actions = _doc_actions_toolbar(website.slug, filename)
            doc_html = _render_page(
                site_title=website.title,
                page_title=label,
                content=f'{doc_actions}<div class="tei-body">{doc_body}</div>',
                style=doc_style,
                navbar=navbar("../"),
                breadcrumb=_render_breadcrumb(doc_crumbs),
                footer_note=footer_note,
                identifier_url=identifier_url,
                tei_valid_badge=tei_valid_badge,
                custom_js=custom_js,
                include_jquery=include_jquery,
                website_slug=slug,
                static_media_collected=referenced_media,
                static_media_prefix="../media/",
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
            tei_valid_badge=tei_valid_badge,
            custom_js=custom_js,
            include_jquery=include_jquery,
            website_slug=slug,
            static_media_collected=referenced_media,
            static_media_prefix="../media/",
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
            tei_valid_badge=tei_valid_badge,
            meta_tags=meta_tags,
            custom_js=custom_js,
            include_jquery=include_jquery,
            website_slug=slug,
            static_media_collected=referenced_media,
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

    # Copy every ``media://`` file referenced by any rendered page into
    # ``site_dir/media/``. Files not referenced stay out of the build,
    # keeping the static tree lean.
    from app.services import website_media as _wm

    _wm.copy_referenced_media_to_build(slug, site_dir, referenced_media)


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
    ``/sites/{slug}/`` so that navbar and content links resolve
    correctly regardless of which static file is being served.
    """
    slug = website.slug
    theme = website.theme_config or {}
    logo_url: str | None = theme.get("logo_url") or None
    base = f"/sites/{slug}"

    site_dir = settings.websites_root / slug
    if not site_dir.resolve().is_relative_to(settings.websites_root.resolve()):
        raise DomainValidationError(code="INVALID_SLUG", message="Slug resolves outside the allowed directory")
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "pages").mkdir(exist_ok=True)


    style = _style_block(theme, website.custom_css)
    custom_js = website.custom_js
    include_jquery = website.include_jquery
    visible_pages = [p for p in website.pages if not p.is_hidden]

    aracne_nav = _parse_aracne_nav(website.nav_config or [])
    _nav_map = {ap["id"]: ap for ap in aracne_nav}
    browse_hidden: bool = bool(_nav_map.get("browse", {}).get("is_hidden", False))
    indices_hidden: bool = bool(_nav_map.get("indices", {}).get("is_hidden", False))
    bibliography_hidden: bool = bool(_nav_map.get("bibliography", {}).get("is_hidden", False))
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

    meta_tags: str = _build_meta_tags(website.meta_config or {}, website_url=website.website_url)
    footer_note, identifier_url = _footer_parts(col)
    tei_valid_badge = await _tei_valid_badge_html(db, col)

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
        tei_valid_badge=tei_valid_badge,
        meta_tags=meta_tags,
        custom_js=custom_js,
        include_jquery=include_jquery,
        website_slug=slug,
        body_class=home_body_class(theme),
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
            tei_valid_badge=tei_valid_badge,
            meta_tags=meta_tags,
            custom_js=custom_js,
            include_jquery=include_jquery,
            website_slug=slug,
        )
        (site_dir / "browse.html").write_text(browse_html, encoding="utf-8")

    # ── bibliography.html — public bibliography (skipped when hidden) ────────
    if not bibliography_hidden:
        from app.models.collection_bibliography import CollectionBibliography as _CB
        bib_xml_h: str | None = None
        if website.collection_id is not None:
            bib_row_h = await db.scalar(
                select(_CB).where(
                    _CB.collection_id == website.collection_id,
                    _CB.is_public.is_(True),
                )
            )
            if bib_row_h is not None:
                bib_xml_h = bib_row_h.content
        hybrid_doc_set = {d["filename"] for d in doc_infos}
        bibliography_html = _render_page(
            site_title=website.title,
            page_title="Bibliography",
            content=_build_bibliography_content(
                bib_xml_h,
                available_filenames=hybrid_doc_set,
                doc_url_for=lambda fn: f"{base}/docs/{fn}",
            ),
            style=style,
            navbar=_navbar(),
            breadcrumb=_render_breadcrumb([(f"{base}/", "Home"), (None, "Bibliography")]),
            footer_note=footer_note,
            identifier_url=identifier_url,
            tei_valid_badge=tei_valid_badge,
            meta_tags=meta_tags,
            custom_js=custom_js,
            include_jquery=include_jquery,
            website_slug=slug,
        )
        (site_dir / "bibliography.html").write_text(bibliography_html, encoding="utf-8")

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
            tei_valid_badge=tei_valid_badge,
            custom_js=custom_js,
            include_jquery=include_jquery,
            website_slug=slug,
        )
        (site_dir / "pages" / f"{page.slug}.html").write_text(
            page_html, encoding="utf-8"
        )

    # ── indices.html — aggregated indices page (skipped when hidden or empty) ─
    built_indices = [idx for idx in (website.indices or []) if idx.cached_data is not None]
    if not indices_hidden and built_indices:
        indices_page_html = render_all_indices_html(website, site_base_url=base)
        (site_dir / "indices.html").write_text(indices_page_html, encoding="utf-8")

    # No media-file copy step here: HYBRID pages reference managed
    # media through the absolute API URL (see ``_render_page`` +
    # ``rewrite_media_refs`` in dynamic mode) so nothing needs to live
    # on disk alongside the HTML.

    # After build, invalidate the dynamic render cache so any cached doc pages
    # are refreshed from eXist-db on the next request.
    invalidate_cache(slug)
