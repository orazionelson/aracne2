"""Websites router — [D+] access (Designer, EditorInChief, Admin).

Endpoints
---------
GET    /websites                              list all websites
POST   /websites                              create a website
GET    /websites/{slug}                       get a website (with pages)
PUT    /websites/{slug}                       update website metadata
DELETE /websites/{slug}                       delete website + static files
POST   /websites/{slug}/build                 trigger static build (STATIC mode)
POST   /websites/{slug}/clear-cache [D+]      invalidate dynamic render cache
POST   /websites/{slug}/preview-doc/{file}    admin XSLT preview
POST   /websites/{slug}/pages                 add a free page
PUT    /websites/{slug}/pages/{page_slug}     update a page
DELETE /websites/{slug}/pages/{page_slug}     delete a page

Public site serving (all rendering modes):
GET    /sites/{slug}/                         cover / index page
GET    /sites/{slug}/browse                   document list
GET    /sites/{slug}/browse.html              alias (backward compat)
GET    /sites/{slug}/search                   search page / results (?q=term)
GET    /sites/{slug}/docs/{filename}          single document (XSLT applied)
GET    /sites/{slug}/pages/{page_slug}        free Markdown pages
GET    /sites/{slug}/{path:path}              static assets (CSS/JS/images)
"""

import mimetypes
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthorizationError, NotFoundError
from app.db.postgres import get_async_session
from app.middleware.acl import ROLE_LEVEL, get_current_user
from app.models.user import User
from app.models.website import RenderingMode
from app.schemas.websites import (
    MetaSuggestionsResponse,
    WebsiteBuildResponse,
    WebsiteCreate,
    WebsitePageCreate,
    WebsitePageResponse,
    WebsitePageUpdate,
    WebsitePreviewDocRequest,
    WebsiteResponse,
    WebsiteUpdate,
)
from app.services import websites as svc

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


# ── Website CRUD ──────────────────────────────────────────────────────────────

@router.get("/websites", response_model=dict)
async def list_websites(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    websites = await svc.list_websites(db)
    return {"data": [WebsiteResponse.model_validate(w) for w in websites]}


@router.post("/websites", status_code=201, response_model=dict)
async def create_website(
    body: WebsiteCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    website = await svc.create_website(db, body, user.id)
    return {"data": WebsiteResponse.model_validate(website)}


@router.get("/websites/{slug}", response_model=dict)
async def get_website(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    website = await svc.get_website(db, slug)
    return {"data": WebsiteResponse.model_validate(website)}


@router.get("/websites/{slug}/meta-suggestions", response_model=dict)
async def get_meta_suggestions(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    suggestions = await svc.get_meta_suggestions(db, slug, user)
    return {"data": MetaSuggestionsResponse.model_validate(suggestions)}


@router.put("/websites/{slug}", response_model=dict)
async def update_website(
    slug: str,
    body: WebsiteUpdate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    website = await svc.update_website(db, slug, body)
    return {"data": WebsiteResponse.model_validate(website)}


@router.delete("/websites/{slug}", status_code=204)
async def delete_website(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> None:
    await svc.delete_website(db, slug)


# ── Build trigger ─────────────────────────────────────────────────────────────

@router.post("/websites/{slug}/build", response_model=dict)
async def trigger_build(
    slug: str,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    """Trigger a static site build.  Returns immediately; build runs in background."""
    await svc.trigger_build(db, slug)
    background_tasks.add_task(svc.run_build, slug)
    return {
        "data": WebsiteBuildResponse(
            slug=slug,
            build_status="pending",
            message="Build queued.",
        )
    }


# ── Cache management ─────────────────────────────────────────────────────────

@router.post("/websites/{slug}/clear-cache", response_model=dict)
async def clear_cache(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    """Invalidate all cached rendered pages and XSLT transform for *slug*.

    Safe to call at any time; does not trigger a build.  Useful after
    manual changes to eXist-db content that should be visible immediately.
    """
    await svc.get_website(db, slug)  # 404 guard
    svc.invalidate_cache(slug)
    return {"data": {"cleared": True}}


# ── XSLT preview ─────────────────────────────────────────────────────────────

@router.post("/websites/{slug}/preview-doc/{filename}", response_model=dict)
async def preview_doc(
    slug: str,
    filename: str,
    body: WebsitePreviewDocRequest,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    """Apply the configured XSLT to a single document and return body HTML.

    Pass xslt_config in the request body to preview unsaved stylesheet changes.
    Omit it (or set to null) to use the website's currently saved xslt_config.
    """
    html = await svc.preview_document(db, slug, filename, body.xslt_config)
    return {"data": {"html": html}}


# ── Pages ─────────────────────────────────────────────────────────────────────

@router.post("/websites/{slug}/pages", status_code=201, response_model=dict)
async def create_page(
    slug: str,
    body: WebsitePageCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    website = await svc.get_website(db, slug)
    page = await svc.create_website_page(db, website.id, body)
    return {"data": WebsitePageResponse.model_validate(page)}


@router.put("/websites/{slug}/pages/{page_slug}", response_model=dict)
async def update_page(
    slug: str,
    page_slug: str,
    body: WebsitePageUpdate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> dict:
    website = await svc.get_website(db, slug)
    page = await svc.update_website_page(db, website.id, page_slug, body)
    return {"data": WebsitePageResponse.model_validate(page)}


@router.delete("/websites/{slug}/pages/{page_slug}", status_code=204)
async def delete_page(
    slug: str,
    page_slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    user: DesignerPlus,
) -> None:
    website = await svc.get_website(db, slug)
    await svc.delete_website_page(db, website.id, page_slug)


# ── Public site serving (all rendering modes) ─────────────────────────────────
#
# STATIC  → FileResponse from pre-built files on disk.
# DYNAMIC → Rendered on every request from eXist-db data; HTML cached in memory.
# HYBRID  → Structural pages (index, browse, search, pages) served from disk
#            like STATIC.  Document pages (/docs/{filename}) always rendered
#            dynamically, even if a static file exists at that path.
#
# ETag headers are added to all dynamic responses so CDN / browser caches can
# skip the body on subsequent requests.  The ETag changes whenever the website
# metadata is updated via PUT /websites/{slug}.

def _resolve_site_file(slug: str, path: str = "index.html") -> Path:
    """Resolve a path inside the site directory, guarding against traversal."""
    root = settings.websites_root.resolve()
    candidate = (root / slug / path).resolve()
    # Ensure the resolved path stays within the site root.
    if not str(candidate).startswith(str(root)):
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


@router.get("/sites/{slug}", include_in_schema=False)
async def serve_site_index_redirect(slug: str) -> RedirectResponse:
    # Redirect to the canonical URL with trailing slash so that relative links
    # inside the generated HTML (e.g. docs/foo.xml.html) resolve correctly.
    return RedirectResponse(url=f"/api/v1/sites/{slug}/", status_code=301)


@router.get("/sites/{slug}/", include_in_schema=False)
async def serve_site_index(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    website = await svc.get_website(db, slug)
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
    return RedirectResponse(url=f"/api/v1/sites/{slug}/browse", status_code=301)


@router.get("/sites/{slug}/browse", include_in_schema=False)
async def serve_site_browse(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    website = await svc.get_website(db, slug)
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
    q: str = "",
) -> Response:
    website = await svc.get_website(db, slug)
    if website.rendering_mode in (RenderingMode.STATIC, RenderingMode.HYBRID):
        path = _resolve_site_file(slug, "search.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page not found.")
        return FileResponse(path, media_type="text/html")
    html = await svc.render_dynamic_search(db, website, q)
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/docs/{filename:path}", include_in_schema=False)
async def serve_site_doc(
    slug: str,
    filename: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    website = await svc.get_website(db, slug)
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
) -> Response:
    website = await svc.get_website(db, slug)
    if website.rendering_mode in (RenderingMode.STATIC, RenderingMode.HYBRID):
        path = _resolve_site_file(slug, f"pages/{page_slug}.html")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Page not found.")
        return FileResponse(path, media_type="text/html")
    try:
        html = await svc.render_dynamic_page(db, website, page_slug)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _dynamic_html_response(html, svc.compute_etag(website), request)


@router.get("/sites/{slug}/{path:path}", include_in_schema=False)
async def serve_site_file(slug: str, path: str) -> FileResponse:
    """Catch-all for static assets (CSS, JS, images).

    Dynamic/Hybrid sites may still have static assets (logo, CSS overrides)
    placed in the site directory by the Designer.
    """
    resolved = _resolve_site_file(slug, path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    media_type, _ = mimetypes.guess_type(str(resolved))
    return FileResponse(resolved, media_type=media_type or "application/octet-stream")
