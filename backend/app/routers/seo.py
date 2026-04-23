"""SEO router — ``/sitemap.xml``, ``/sitemap-*.xml``, ``/robots.txt``.

These endpoints intentionally live under ``/api/v1`` like the rest of
the backend; nginx (and the Vite dev-server) rewrite the canonical
root-level paths (``/robots.txt``, ``/sitemap.xml``) to their ``/api/v1``
siblings so crawlers find them where they expect.

All endpoints are **public** (no auth) and **light on state**: every
sitemap is built on request from the database (plus eXist-db for
document enumeration), with fail-soft behaviour on external-service
hiccups so a momentary eXist-db outage does not take the sitemap
offline.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient
from app.db.postgres import get_async_session
from app.dependencies import get_existdb
from app.services.seo import (
    SitemapEntry,
    build_core_entries,
    build_robots_txt,
    build_search_engine_entries,
    build_website_entries,
    serialize_index,
    serialize_urlset,
)
from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()

router = APIRouter(tags=["seo"])

_SITEMAP_HEADERS = {
    # Sitemap protocol prefers application/xml; include charset explicitly
    # so non-standard crawlers do not re-detect.
    "Content-Type": "application/xml; charset=utf-8",
    # Don't burn through the crawler's cache — 1h is enough to smooth load
    # spikes without keeping stale content around for long.
    "Cache-Control": "public, max-age=3600",
}


async def _public_base_url(request: Request, db: AsyncSession) -> str:
    """Canonical origin for crawler URLs.

    Prefers the ``public_base_url`` system_setting (the value editors
    configure explicitly for deposit / LOD purposes); falls back to the
    request's scheme+host when unset. Always returned without trailing
    slash so callers can concatenate with ``/browse/…`` cleanly.
    """
    configured = (await get_decrypted_setting(db, "public_base_url") or "").strip().rstrip("/")
    if configured:
        return configured
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")


async def _include_search_engines(db: AsyncSession) -> bool:
    raw = (await get_decrypted_setting(db, "sitemap_include_search_engines") or "").strip()
    return raw == "true"


async def _home_enabled(db: AsyncSession) -> bool:
    raw = (await get_decrypted_setting(db, "public_home_enabled") or "").strip()
    return raw == "true"


@router.get("/sitemap.xml")
async def sitemap_index(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Root sitemap — an **index** pointing to sub-sitemaps.

    Keeps the XML light on wire and lets crawlers poll only the
    sections that changed between visits.
    """
    base = await _public_base_url(request, db)
    entries: list[SitemapEntry] = [
        SitemapEntry(loc=f"{base}/sitemap-core.xml"),
        SitemapEntry(loc=f"{base}/sitemap-websites.xml"),
    ]
    if await _include_search_engines(db):
        entries.append(SitemapEntry(loc=f"{base}/sitemap-search-engines.xml"))
    return Response(serialize_index(entries), headers=_SITEMAP_HEADERS)


@router.get("/sitemap-core.xml")
async def sitemap_core(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> Response:
    """Published public collections + their documents (+ optional public home)."""
    base = await _public_base_url(request, db)
    entries = await build_core_entries(
        db, existdb, base, include_home=await _home_enabled(db)
    )
    return Response(serialize_urlset(entries), headers=_SITEMAP_HEADERS)


@router.get("/sitemap-websites.xml")
async def sitemap_websites(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """All published websites: landing + browse + visible pages."""
    base = await _public_base_url(request, db)
    entries = await build_website_entries(db, base)
    return Response(serialize_urlset(entries), headers=_SITEMAP_HEADERS)


@router.get("/sitemap-search-engines.xml")
async def sitemap_search_engines(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Built search pages. Empty urlset when the opt-in setting is off.

    Returning an empty-but-valid sitemap (rather than 404) avoids
    noisy logs in crawler status reports when an admin flips the
    toggle off — the discovered URL stays reachable.
    """
    base = await _public_base_url(request, db)
    if not await _include_search_engines(db):
        return Response(serialize_urlset([]), headers=_SITEMAP_HEADERS)
    entries = await build_search_engine_entries(db, base)
    return Response(serialize_urlset(entries), headers=_SITEMAP_HEADERS)


@router.get("/robots.txt")
async def robots_txt(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> PlainTextResponse:
    """Platform robots.txt — permissive on public paths, disallow admin,
    and point every crawler at the sitemap index."""
    base = await _public_base_url(request, db)
    return PlainTextResponse(
        build_robots_txt(base),
        headers={"Cache-Control": "public, max-age=3600"},
    )
