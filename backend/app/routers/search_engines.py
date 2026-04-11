"""Search engines router.

Endpoints
---------
Management [D+] (Designer, EditorInChief, Admin):
GET    /search-engines                       list all search engines
POST   /search-engines                       create a search engine
GET    /search-engines/{slug}                get a search engine
PUT    /search-engines/{slug}                update a search engine
DELETE /search-engines/{slug}                delete a search engine
GET    /search-engines/public-collections    list published+public collections
POST   /search-engines/{slug}/build          trigger HTML page build
POST   /search-engines/{slug}/cache/clear    clear query cache

Public [pub]:
GET    /search-pages/{slug}/                 serve built HTML search page
GET    /search-pages/{slug}/advanced/        serve built advanced search page
GET    /search-engines/{slug}/search         full-text search (?q=...&collections=...&max_results=...)
GET    /search-engines/{slug}/advanced-search  advanced structural/attribute search
"""

from pathlib import Path
from typing import Annotated

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthorizationError, NotFoundError
from app.db.postgres import get_async_session
from app.middleware.acl import ROLE_LEVEL, get_current_user
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.search_engines import (
    SearchEngineCreate,
    SearchEngineSearchResponse,
    SearchEngineUpdate,
)
from app.services import search_engines as svc
from app.services.embed import list_embed_logs

router = APIRouter(tags=["search-engines"])


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


# ── Management endpoints [D+] ─────────────────────────────────────────────────

@router.get("/search-engines/public-collections")
async def list_public_collections(
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """List all published + public collections available for search engine assignment."""
    cols = await svc.list_public_collections(db)
    return {"data": cols}


@router.get("/search-engines", response_model=None)
async def list_search_engines(
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    engines = await svc.list_search_engines(db)
    return {"data": [e.model_dump(mode="json") for e in engines]}


@router.post("/search-engines", status_code=201, response_model=None)
async def create_search_engine(
    payload: SearchEngineCreate,
    user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    engine = await svc.create_search_engine(db, payload, created_by=user.id)
    return {"data": engine.model_dump(mode="json")}


@router.get("/search-engines/{slug}", response_model=None)
async def get_search_engine(
    slug: str,
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    engine = await svc.get_search_engine(db, slug)
    return {"data": engine.model_dump(mode="json")}


@router.put("/search-engines/{slug}", response_model=None)
async def update_search_engine(
    slug: str,
    payload: SearchEngineUpdate,
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    engine = await svc.update_search_engine(db, slug, payload)
    return {"data": engine.model_dump(mode="json")}


@router.delete("/search-engines/{slug}", status_code=204)
async def delete_search_engine(
    slug: str,
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await svc.delete_search_engine(db, slug)


@router.post("/search-engines/{slug}/cache/clear", response_model=None)
async def clear_search_engine_cache(
    slug: str,
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Invalidate all cached query results for the search engine."""
    deleted = await svc.clear_cache(db, slug)
    return {"data": {"deleted": deleted}}


# ── Available tags [D+] ──────────────────────────────────────────────────────

@router.get("/search-engines/{slug}/available-tags", response_model=None)
async def get_available_tags(
    slug: str,
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Return the merged element→attributes map across all linked collections.

    Used by the admin UI to populate autocomplete suggestions in the
    advanced search config panel.  Results are computed on every request
    (no caching) and are only accessible to Designer-plus users.
    """
    tags = await svc.get_available_tags(db, slug)
    return {"data": tags}


# ── Embed logs [D+] ─────────────────────────────────────────────────────────

@router.get("/search-engines/{slug}/embed-logs", response_model=None)
async def get_embed_logs(
    slug: str,
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Return paginated embed request logs for a search engine."""
    result = await list_embed_logs(db, slug, page, per_page)
    return result.model_dump(mode="json")


# ── Build endpoint [D+] ──────────────────────────────────────────────────────

@router.post("/search-engines/{slug}/build", response_model=None)
async def build_search_engine(
    slug: str,
    background_tasks: BackgroundTasks,
    _user: DesignerPlus,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict:
    """Trigger an async HTML build for the search engine page."""
    engine = await svc.trigger_build(db, slug)
    background_tasks.add_task(svc._do_build, slug)
    return {"data": engine.model_dump(mode="json")}


# ── Public page serve endpoints [pub] ────────────────────────────────────────

@router.get("/search-pages/{slug}/", response_class=HTMLResponse)
async def serve_search_page(slug: str) -> FileResponse:
    """Serve the built HTML search page for the given search engine slug."""
    index = settings.search_engines_root / slug / "index.html"
    if not index.is_file():
        raise NotFoundError(f"Search page for '{slug}' has not been built yet")
    return FileResponse(str(index), media_type="text/html")


@router.get("/search-pages/{slug}/advanced/", response_class=HTMLResponse)
async def serve_advanced_search_page(slug: str) -> FileResponse:
    """Serve the built advanced search page for the given search engine slug."""
    index = settings.search_engines_root / slug / "advanced" / "index.html"
    if not index.is_file():
        raise NotFoundError(
            f"Advanced search page for '{slug}' has not been built yet"
        )
    return FileResponse(str(index), media_type="text/html")


# ── Public search endpoints [pub] ─────────────────────────────────────────────

@router.get("/search-engines/{slug}/search", response_model=None)
@limiter.limit("60/minute")
async def search(
    slug: str,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    q: str = Query(..., min_length=1, max_length=512, description="Search query"),
    collections: str | None = Query(
        None,
        description="Comma-separated collection slugs to restrict search (default: all linked)",
    ),
    max_results: int = Query(50, ge=1, le=200, description="Maximum hits to return"),
) -> dict:
    """Public full-text search endpoint for a search engine."""
    col_slugs: list[str] | None = None
    if collections:
        col_slugs = [s.strip() for s in collections.split(",") if s.strip()]

    result, ttl_minutes = await svc.run_search(db, slug, q, col_slugs, max_results)
    if ttl_minutes > 0:
        response.headers["Cache-Control"] = f"public, max-age={ttl_minutes * 60}"
    else:
        response.headers["Cache-Control"] = "no-store"
    return {"data": result.model_dump(mode="json")}


@router.get("/search-engines/{slug}/advanced-search", response_model=None)
@limiter.limit("60/minute")
async def advanced_search(
    slug: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    q: str | None = Query(None, max_length=512, description="Text to search within the element"),
    element: str | None = Query(
        None,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9._-]*$",
        description="Element local-name to restrict text search (e.g. persName)",
    ),
    attr_name: str | None = Query(
        None,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9._-]*$",
        description="Attribute local-name to filter on",
    ),
    attr_value: str | None = Query(
        None, max_length=256, description="Attribute value to match (empty = any)"
    ),
    collections: str | None = Query(
        None,
        description="Comma-separated collection slugs to restrict search (default: all linked)",
    ),
    max_results: int = Query(50, ge=1, le=200, description="Maximum hits to return"),
) -> dict:
    """Public advanced structural/attribute search endpoint for a search engine.

    At least one of q, element, or attr_name must be provided.
    Results are not cached (advanced queries are typically specific/infrequent).
    """
    col_slugs: list[str] | None = None
    if collections:
        col_slugs = [s.strip() for s in collections.split(",") if s.strip()]

    result = await svc.run_advanced_search(
        db,
        slug=slug,
        q=q,
        element_name=element,
        attr_name=attr_name,
        attr_value=attr_value,
        collection_slugs=col_slugs,
        max_results=max_results,
    )
    return {"data": result.model_dump(mode="json")}
