"""Websites router — [D+] access (Designer, EditorInChief, Admin).

Endpoints
---------
GET    /websites                                      list all websites
POST   /websites                                      create a website
GET    /websites/{slug}                               get a website (with pages + indices)
PUT    /websites/{slug}                               update website metadata
DELETE /websites/{slug}                               delete website + static files
POST   /websites/{slug}/build                         trigger static build (STATIC mode)
GET    /websites/{slug}/download [D+]                 download built STATIC site as ZIP
POST   /websites/{slug}/clear-cache [D+]              invalidate dynamic render cache
POST   /websites/{slug}/preview-doc/{file}            admin XSLT preview
POST   /websites/{slug}/pages                         add a free page
PUT    /websites/{slug}/pages/{page_slug}             update a page
DELETE /websites/{slug}/pages/{page_slug}             delete a page
GET    /websites/{slug}/tags [D+]                     get cached distinct-tag list
POST   /websites/{slug}/tags/refresh [D+]             re-run distinct-tag XQuery
GET    /websites/{slug}/indices [D+]                  list configured indices
POST   /websites/{slug}/indices [D+]                  create an index
PUT    /websites/{slug}/indices/{index_id} [D+]       update an index
DELETE /websites/{slug}/indices/{index_id} [D+]       delete an index
POST   /websites/{slug}/indices/{index_id}/rebuild    rebuild one index cache
POST   /websites/{slug}/indices/rebuild-all           rebuild all indices cache

Public site serving (all rendering modes):
GET    /sites/{slug}/                         cover / index page
GET    /sites/{slug}/browse                   document list
GET    /sites/{slug}/browse.html              alias (backward compat)
GET    /sites/{slug}/search                   search page / results (?q=term)
GET    /sites/{slug}/docs/{filename}          single document (XSLT applied)
GET    /sites/{slug}/pages/{page_slug}        free Markdown pages
GET    /sites/{slug}/index/{label}/           rendered index page
GET    /sites/{slug}/{path:path}              static assets (CSS/JS/images)
"""

import asyncio
import io
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import ROLE_LEVEL
from app.core.exceptions import AuthorizationError, NotFoundError
from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user, get_optional_user
from app.models.user import User
from app.models.website import BuildStatus, RenderingMode, Website
from app.schemas.common import DataResponse
from app.schemas.websites import (
    MetaSuggestionsResponse,
    WebsiteBuildResponse,
    WebsiteCacheClearedResponse,
    WebsiteCreate,
    WebsiteIndexCreate,
    WebsiteIndexResponse,
    WebsiteIndexUpdate,
    WebsitePageCreate,
    WebsitePageResponse,
    WebsitePageUpdate,
    WebsitePreviewDocRequest,
    WebsitePreviewDocResponse,
    WebsiteResponse,
    WebsiteTagsResponse,
    WebsiteUpdate,
)
from app.services import websites as svc
from app.services import website_media as media_svc
from app.services.uploads import read_capped
from app.schemas.websites import WebsiteMediaFile

logger = structlog.get_logger()

router = APIRouter(tags=["websites"])


# ── ACL dependency ────────────────────────────────────────────────────────────

async def _require_designer_plus(
    user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> User:
    """[D+]: Designer, EditorInChief, Admin.

    Designer is a lateral role at level 2, equal to Editor.  A plain
    min_level check would include Editor too.  We therefore require either
    the exact Designer role OR level >= EditorInChief (3).
    """
    role: str = getattr(request.state, "role", "User")
    user_level = ROLE_LEVEL.get(role, 0)
    if role != "Designer" and user_level < ROLE_LEVEL["EditorInChief"]:
        raise AuthorizationError()
    return user


DesignerPlus = Annotated[User, Depends(_require_designer_plus)]

# Optional authenticated user — used by public /sites/ routes so unpublished
# sites are still accessible to staff (Editor and above, level >= 2).
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def _check_site_access(website: Website, user: User | None, request: Request) -> None:
    """Raise 404 if the site is not published and the caller is not staff.

    Unpublished sites are visible to any authenticated user with level >= 2
    (Editor, Designer, EditorInChief, Admin).  Anonymous visitors and plain
    Users (level 1) receive a 404 — indistinguishable from a missing site so
    as not to leak its existence.
    """
    if website.is_published:
        return
    if user is None:
        raise HTTPException(status_code=404, detail="Site not found.")
    role: str = getattr(request.state, "role", "User")
    if ROLE_LEVEL.get(role, 0) < 2:
        raise HTTPException(status_code=404, detail="Site not found.")


# ── Website CRUD ──────────────────────────────────────────────────────────────

@router.get("/websites")
async def list_websites(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[list[WebsiteResponse]]:
    websites = await svc.list_websites(db)
    return DataResponse(data=[WebsiteResponse.model_validate(w) for w in websites])


@router.post("/websites", status_code=201)
async def create_website(
    body: WebsiteCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteResponse]:
    website = await svc.create_website(db, body, user.id)
    return DataResponse(data=WebsiteResponse.model_validate(website))


@router.get("/websites/{slug}")
async def get_website(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteResponse]:
    website = await svc.get_website(db, slug)
    return DataResponse(data=WebsiteResponse.model_validate(website))


@router.get("/websites/{slug}/meta-suggestions")
async def get_meta_suggestions(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[MetaSuggestionsResponse]:
    """Return XQuery-derived metadata suggestions for the linked collection.

    Suggestions are pre-computed from existing documents (authors, publishers,
    etc.) to speed up the metadata edit form.
    """
    suggestions = await svc.get_meta_suggestions(db, slug, user)
    return DataResponse(data=MetaSuggestionsResponse.model_validate(suggestions))


@router.put("/websites/{slug}")
async def update_website(
    slug: str,
    body: WebsiteUpdate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteResponse]:
    website = await svc.update_website(db, slug, body)
    return DataResponse(data=WebsiteResponse.model_validate(website))


@router.delete("/websites/{slug}", status_code=204)
async def delete_website(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> None:
    """Delete a website record and remove its static files from disk."""
    await svc.delete_website(db, slug)


# ── Build trigger ─────────────────────────────────────────────────────────────

@router.post("/websites/{slug}/build")
async def trigger_build(
    slug: str,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteBuildResponse]:
    """Trigger a static site build.  Returns immediately; build runs in background."""
    await svc.trigger_build(db, slug)
    background_tasks.add_task(svc.run_build, slug)
    return DataResponse(
        data=WebsiteBuildResponse(
            slug=slug,
            build_status="pending",
            message="Build queued.",
        )
    )


# ── ZIP download (STATIC only) ────────────────────────────────────────────────

@router.get("/websites/{slug}/download")
async def download_site(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> Response:
    """Return the built STATIC site as a downloadable ZIP archive.

    Only available for STATIC sites whose build_status is *done*.
    """
    website = await svc.get_website(db, slug)
    if website.rendering_mode != RenderingMode.STATIC:
        raise HTTPException(
            status_code=400,
            detail="Only STATIC sites can be downloaded as a ZIP.",
        )
    if website.build_status != BuildStatus.done:
        raise HTTPException(status_code=409, detail="Site has not been built yet.")

    site_dir = settings.websites_root / slug
    if not site_dir.exists():
        raise HTTPException(status_code=404, detail="Site directory not found.")

    def _make_zip() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in site_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(site_dir))
        return buf.getvalue()

    zip_bytes = await asyncio.to_thread(_make_zip)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


# ── Cache management ─────────────────────────────────────────────────────────

@router.post("/websites/{slug}/clear-cache")
async def clear_cache(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteCacheClearedResponse]:
    """Invalidate all cached rendered pages and XSLT transform for *slug*.

    Safe to call at any time; does not trigger a build.  Useful after
    manual changes to eXist-db content that should be visible immediately.
    """
    await svc.get_website(db, slug)  # 404 guard
    svc.invalidate_cache(slug)
    return DataResponse(data=WebsiteCacheClearedResponse(cleared=True))


# ── XSLT preview ─────────────────────────────────────────────────────────────

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


@router.post("/websites/{slug}/preview-doc/{filename}")
async def preview_doc(
    slug: str,
    filename: str,
    body: WebsitePreviewDocRequest,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsitePreviewDocResponse]:
    """Apply the configured XSLT to a single document and return body HTML.

    Pass xslt_config in the request body to preview unsaved stylesheet changes.
    Omit it (or set to null) to use the website's currently saved xslt_config.
    """
    if not _SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    html = await svc.preview_document(db, slug, filename, body.xslt_config)
    return DataResponse(data=WebsitePreviewDocResponse(html=html))


# ── Pages ─────────────────────────────────────────────────────────────────────

@router.post("/websites/{slug}/pages", status_code=201)
async def create_page(
    slug: str,
    body: WebsitePageCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsitePageResponse]:
    website = await svc.get_website(db, slug)
    page = await svc.create_website_page(db, website.id, body)
    return DataResponse(data=WebsitePageResponse.model_validate(page))


@router.put("/websites/{slug}/pages/{page_slug}")
async def update_page(
    slug: str,
    page_slug: str,
    body: WebsitePageUpdate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsitePageResponse]:
    website = await svc.get_website(db, slug)
    page = await svc.update_website_page(db, website.id, page_slug, body)
    return DataResponse(data=WebsitePageResponse.model_validate(page))


@router.delete("/websites/{slug}/pages/{page_slug}", status_code=204)
async def delete_page(
    slug: str,
    page_slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> None:
    website = await svc.get_website(db, slug)
    await svc.delete_website_page(db, website.id, page_slug)


# ── Tag discovery ─────────────────────────────────────────────────────────────

@router.get("/websites/{slug}/tags")
async def get_website_tags(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteTagsResponse]:
    """Return the cached distinct-tag map for this website's collection.

    The map is populated by POST /tags/refresh.  Returns null when no refresh
    has been run yet.
    """
    website = await svc.get_website(db, slug)
    return DataResponse(
        data=WebsiteTagsResponse(
            distinct_tags=website.distinct_tags,
            tags_refreshed_at=website.tags_refreshed_at,
        )
    )


@router.post("/websites/{slug}/tags/refresh")
async def refresh_website_tags(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteTagsResponse]:
    """Re-run the distinct-tag XQuery against the linked collection and cache the result."""
    website = await svc.refresh_website_tags(db, slug)
    return DataResponse(
        data=WebsiteTagsResponse(
            distinct_tags=website.distinct_tags,
            tags_refreshed_at=website.tags_refreshed_at,
        )
    )


# ── Website indices ───────────────────────────────────────────────────────────

@router.get("/websites/{slug}/indices")
async def list_indices(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[list[WebsiteIndexResponse]]:
    website = await svc.get_website(db, slug)
    indices = await svc.list_website_indices(db, website.id)
    return DataResponse(data=[WebsiteIndexResponse.model_validate(i) for i in indices])


@router.post("/websites/{slug}/indices", status_code=201)
async def create_index(
    slug: str,
    body: WebsiteIndexCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteIndexResponse]:
    website = await svc.get_website(db, slug)
    idx = await svc.create_website_index(db, website.id, body)
    return DataResponse(data=WebsiteIndexResponse.model_validate(idx))


@router.put("/websites/{slug}/indices/{index_id}")
async def update_index(
    slug: str,
    index_id: str,
    body: WebsiteIndexUpdate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteIndexResponse]:
    import uuid as _uuid
    website = await svc.get_website(db, slug)
    idx = await svc.update_website_index(db, website.id, _uuid.UUID(index_id), body)
    return DataResponse(data=WebsiteIndexResponse.model_validate(idx))


@router.delete("/websites/{slug}/indices/{index_id}", status_code=204)
async def delete_index(
    slug: str,
    index_id: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> None:
    import uuid as _uuid
    website = await svc.get_website(db, slug)
    await svc.delete_website_index(db, website.id, _uuid.UUID(index_id))


@router.post("/websites/{slug}/indices/rebuild-all")
async def rebuild_all_indices(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[list[WebsiteIndexResponse]]:
    """Rebuild all configured indices for this website.  Synchronous."""
    indices = await svc.rebuild_all_website_indices(db, slug)
    return DataResponse(data=[WebsiteIndexResponse.model_validate(i) for i in indices])


@router.post("/websites/{slug}/indices/{index_id}/rebuild")
async def rebuild_index(
    slug: str,
    index_id: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteIndexResponse]:
    """Rebuild the cached data for a single index.  Synchronous."""
    import uuid as _uuid
    idx = await svc.rebuild_website_index(db, slug, _uuid.UUID(index_id))
    return DataResponse(data=WebsiteIndexResponse.model_validate(idx))


# ── Public site serving (all rendering modes) ─────────────────────────────────
#
# STATIC  → FileResponse from pre-built files on disk.
# DYNAMIC → Rendered on every request from eXist-db data; HTML cached in memory.
# HYBRID  → index, browse, pages served from disk (built by _build_hybrid_site).
#            search and docs always rendered dynamically:
#            • search is not built statically — all links point to the dynamic endpoint
#            • docs are always rendered live from eXist-db (never on disk)
#
# ETag headers are added to all dynamic responses so CDN / browser caches can
# skip the body on subsequent requests.  The ETag changes whenever the website
# metadata is updated via PUT /websites/{slug}.

def _resolve_site_file(slug: str, path: str = "index.html") -> Path:
    """Resolve a path inside the site directory, guarding against traversal."""
    site_root = settings.websites_root.resolve() / slug
    candidate = (site_root / path).resolve()
    # Ensure the resolved path stays within this site's directory.
    # is_relative_to() avoids the str.startswith prefix-confusion bug
    # (e.g. /sites/foo matching /sites/foobar).
    if not candidate.is_relative_to(site_root):
        raise HTTPException(status_code=403, detail="Forbidden")
    # Directory → serve index.html
    if candidate.is_dir():
        candidate = candidate / "index.html"
    return candidate


def _dynamic_html_response(html: str, etag: str, request: Request) -> Response:
    """Return 200 HTMLResponse with ETag header, or 304 if ETag matches."""
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return HTMLResponse(html, headers={"ETag": etag, "Vary": "Accept-Encoding"})


_MAINTENANCE_RETRY_AFTER_SECONDS = 3600  # 1 hour — crawlers will ret-try past this


async def _maybe_maintenance_response(
    db: AsyncSession, website: svc.Website,
) -> Response | None:
    """Return a 503 maintenance banner when the site should be hidden;
    return ``None`` otherwise.

    Centralises the check so every site-serving endpoint (dynamic
    render + static file + catch-all) can call it in one line at the
    top. Applies uniformly regardless of ``rendering_mode``.
    """
    if not await svc.is_website_in_maintenance(db, website):
        return None
    html = svc.build_maintenance_html(
        website, admin_email=settings.admin_email,
    )
    return Response(
        content=html,
        status_code=503,
        media_type="text/html",
        headers={
            "Retry-After": str(_MAINTENANCE_RETRY_AFTER_SECONDS),
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


# ── Per-website media library ────────────────────────────────────────────────
#
# Storage is filesystem-only (no DB index). The stable ``media://filename``
# pseudo-URL lives in theme/Markdown/WYSIWYG content and is rewritten to a
# real URL at render/build time by ``website_media.rewrite_media_refs``.


@router.get("/websites/{slug}/media")
async def list_website_media(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[list[WebsiteMediaFile]]:
    """List the media files uploaded for a website [D+]."""
    await svc.get_website(db, slug)  # 404 if the slug is unknown
    files = media_svc.list_media(slug)
    return DataResponse(
        data=[
            WebsiteMediaFile(
                filename=f.filename,
                size_bytes=f.size_bytes,
                content_type=f.content_type,
                uploaded_at=f.uploaded_at,
                ref=f"media://{f.filename}",
            )
            for f in files
        ]
    )


@router.post("/websites/{slug}/media", status_code=201)
async def upload_website_media(
    slug: str,
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> DataResponse[WebsiteMediaFile]:
    """Upload one image into the website's media folder [D+].

    Accepted extensions: jpg / jpeg / png / gif / webp / avif / svg.
    SVG uploads are scrubbed (scripts / event handlers / external refs
    removed) before being written to disk.
    """
    await svc.get_website(db, slug)
    payload = await read_capped(file, media_svc._MAX_UPLOAD_BYTES)
    m = media_svc.save_media(slug, file.filename or "file", payload)
    return DataResponse(
        data=WebsiteMediaFile(
            filename=m.filename,
            size_bytes=m.size_bytes,
            content_type=m.content_type,
            uploaded_at=m.uploaded_at,
            ref=f"media://{m.filename}",
        )
    )


@router.delete("/websites/{slug}/media/{filename}", status_code=204)
async def delete_website_media(
    slug: str,
    filename: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> None:
    """Remove a file from the website's media folder [D+]."""
    await svc.get_website(db, slug)
    media_svc.delete_media(slug, filename)


@router.get("/websites/{slug}/media/{filename}", include_in_schema=False)
async def serve_website_media(
    slug: str,
    filename: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve a media file to site visitors.

    Matches ``_check_site_access`` semantics: anonymous callers see a
    404 on unpublished sites so their existence is not leaked. Staff
    (level >= 2) can preview media on draft sites.
    """
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    payload, content_type = media_svc.read_media(slug, filename)
    # ``Cache-Control: public, max-age=3600`` — media is immutable from
    # the client's point of view (deleting and re-uploading with the
    # same name is rare enough that a 1-hour staleness window is fine).
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/sites/{slug}", include_in_schema=False)
async def serve_site_index_redirect(slug: str) -> RedirectResponse:
    """Redirect to the canonical URL with trailing slash.

    Required so that relative asset links inside generated HTML resolve correctly.
    """
    return RedirectResponse(url=f"/sites/{slug}/", status_code=301)


@router.get("/sites/{slug}/", include_in_schema=False)
async def serve_site_index(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve the site cover page, respecting the rendering mode and access guard."""
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    if website.rendering_mode in (RenderingMode.STATIC, RenderingMode.HYBRID):
        path = _resolve_site_file(slug, "index.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Site not found or not yet built.")
        return FileResponse(path, media_type="text/html")
    # DYNAMIC
    html = await svc.render_dynamic_index(db, website)
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/browse.html", include_in_schema=False)
async def serve_browse_html_compat(slug: str) -> RedirectResponse:
    """Backward-compat alias for static links that include the .html extension."""
    return RedirectResponse(url=f"/sites/{slug}/browse", status_code=301)


@router.get("/sites/{slug}/browse", include_in_schema=False)
async def serve_site_browse(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve the document list page, respecting the rendering mode and access guard."""
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    if website.rendering_mode in (RenderingMode.STATIC, RenderingMode.HYBRID):
        path = _resolve_site_file(slug, "browse.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page not found.")
        return FileResponse(path, media_type="text/html")
    html = await svc.render_dynamic_browse(db, website)
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/search", include_in_schema=False)
async def serve_site_search(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
    q: str = "",
) -> Response:
    """Serve the search results page.

    STATIC: serves a pre-built client-side JS search page.
    DYNAMIC/HYBRID: runs a server-side eXist-db full-text search.
    """
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    if website.rendering_mode == RenderingMode.STATIC:
        # Static path: client-side JS search page built at build time.
        path = _resolve_site_file(slug, "search.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page not found.")
        return FileResponse(path, media_type="text/html")
    # DYNAMIC or HYBRID: server-side eXist-db full-text search.
    # HYBRID does not build search.html — all navbar links point here directly.
    html = await svc.render_dynamic_search(db, website, q)
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/bibliography", include_in_schema=False)
@router.get("/sites/{slug}/bibliography.html", include_in_schema=False)
async def serve_site_bibliography(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve the bibliography page.

    STATIC: serves pre-built bibliography.html from disk.
    DYNAMIC/HYBRID: renders live from the linked collection's public bibliography.
    """
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    if website.rendering_mode == RenderingMode.STATIC:
        path = _resolve_site_file(slug, "bibliography.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page not found.")
        return FileResponse(path, media_type="text/html")
    html = await svc.render_dynamic_bibliography(db, website)
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/docs/{filename}/source", include_in_schema=False)
async def serve_site_doc_source(
    slug: str,
    filename: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Return the raw TEI XML of a document as an attachment.

    Mirrors the access rules of the rendered ``/sites/{slug}/docs/
    {filename}`` endpoint — same site-access check, same maintenance
    short-circuit. ``Content-Disposition: attachment`` triggers a
    download instead of an inline render.

    Declared *before* the catch-all ``/docs/{filename:path}`` route so
    FastAPI matches the more-specific path first.
    """
    from app.db.existdb import existdb_client
    from fastapi.responses import Response as _Response

    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    if website.collection_id is None:
        raise HTTPException(status_code=404, detail="Linked collection not found.")
    from app.models.collection import Collection
    col = await db.get(Collection, website.collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="Linked collection not found.")
    try:
        xml_bytes = await existdb_client.get_document(col.slug, filename)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sites/{slug}/docs/{filename:path}", include_in_schema=False)
async def serve_site_doc(
    slug: str,
    filename: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve a single document with XSLT applied.

    STATIC: serves a pre-built .html file from disk.
    DYNAMIC/HYBRID: renders live from eXist-db on every request.
    """
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    # HYBRID: document pages are always dynamic, even if a static file exists.
    if website.rendering_mode == RenderingMode.STATIC:
        # Static path: look for docs/{filename}.html on disk.
        # Strip trailing .html if already present (handles both forms).
        static_name = filename[:-5] if filename.endswith(".html") else filename
        path = _resolve_site_file(slug, f"docs/{static_name}.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Document not found.")
        return FileResponse(path, media_type="text/html")
    # DYNAMIC or HYBRID — always render live
    try:
        html = await svc.render_dynamic_doc(db, website, filename)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/pages/{page_slug}", include_in_schema=False)
async def serve_site_page(
    slug: str,
    page_slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve a free Markdown page by slug.

    STATIC/HYBRID: serves from disk. DYNAMIC: renders from DB.
    """
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    if website.rendering_mode in (RenderingMode.STATIC, RenderingMode.HYBRID):
        # Strip trailing .html if already present (static links include the extension).
        clean_slug = page_slug[:-5] if page_slug.endswith(".html") else page_slug
        path = _resolve_site_file(slug, f"pages/{clean_slug}.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page not found.")
        return FileResponse(path, media_type="text/html")
    # Dynamic lookup uses the slug without extension.
    lookup_slug = page_slug[:-5] if page_slug.endswith(".html") else page_slug
    try:
        html = await svc.render_dynamic_page(db, website, lookup_slug)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/indices/", include_in_schema=False)
async def serve_site_all_indices(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve the aggregated indices page (all built indices as tabs)."""
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    html = svc.render_all_indices_html(
        website,
        site_base_url=f"/sites/{slug}",
    )
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/index/{label}/", include_in_schema=False)
async def serve_site_index_page(
    slug: str,
    label: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> Response:
    """Serve a rendered index page (public; respects published/preview guard)."""
    import uuid as _uuid
    from sqlalchemy import select as _select
    from app.models.website import WebsiteIndex as _WebsiteIndex

    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint

    idx = await db.scalar(
        _select(_WebsiteIndex).where(
            _WebsiteIndex.website_id == website.id,
            _WebsiteIndex.label == label,
        )
    )
    if idx is None or idx.cached_data is None:
        raise HTTPException(status_code=404, detail="Index not found or not yet built.")

    html = svc.render_website_index_html(website, idx)
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/{path:path}", include_in_schema=False)
async def serve_site_file(
    slug: str,
    path: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: OptionalUser,
) -> FileResponse:
    """Catch-all for static assets (CSS, JS, images).

    Dynamic/Hybrid sites may still have static assets (logo, CSS overrides)
    placed in the site directory by the Designer.
    """
    website = await svc.get_website(db, slug)
    _check_site_access(website, user, request)
    if (maint := await _maybe_maintenance_response(db, website)) is not None:
        return maint
    resolved = _resolve_site_file(slug, path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    media_type, _ = mimetypes.guess_type(str(resolved))
    return FileResponse(resolved, media_type=media_type or "application/octet-stream")
