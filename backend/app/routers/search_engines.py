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

Public [pub]:
GET    /search-engines/{slug}/search         full-text search (?q=...&collections=...&max_results=...)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
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


# ── Public search endpoint [pub] ──────────────────────────────────────────────

@router.get("/search-engines/{slug}/search", response_model=None)
@limiter.limit("60/minute")
async def search(
    slug: str,
    request: Request,
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

    result = await svc.run_search(db, slug, q, col_slugs, max_results)
    return {"data": result.model_dump(mode="json")}
