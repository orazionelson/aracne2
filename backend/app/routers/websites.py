"""Websites router — [D+] access (Designer, EditorInChief, Admin).

Endpoints
---------
GET    /websites                  list all websites
POST   /websites                  create a website
GET    /websites/{slug}           get a website (with pages)
PUT    /websites/{slug}           update website metadata
DELETE /websites/{slug}           delete website + static files
POST   /websites/{slug}/build     trigger static build (Option A)
POST   /websites/{slug}/pages     add a free page
PUT    /websites/{slug}/pages/{page_slug}  update a page
DELETE /websites/{slug}/pages/{page_slug}  delete a page
GET    /sites/{slug}/{path}       serve generated static files (public)
GET    /sites/{slug}              serve site index (public)
"""

import mimetypes
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthorizationError
from app.db.postgres import get_async_session
from app.middleware.acl import ROLE_LEVEL, get_current_user
from app.models.user import User
from app.schemas.websites import (
    WebsiteBuildResponse,
    WebsiteCreate,
    WebsitePageCreate,
    WebsitePageResponse,
    WebsitePageUpdate,
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


# ── Static file serving (public) ──────────────────────────────────────────────

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


@router.get("/sites/{slug}", include_in_schema=False)
async def serve_site_index(slug: str) -> FileResponse:
    path = _resolve_site_file(slug, "index.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Site not found or not yet built.")
    return FileResponse(path, media_type="text/html")


@router.get("/sites/{slug}/{path:path}", include_in_schema=False)
async def serve_site_file(slug: str, path: str) -> FileResponse:
    resolved = _resolve_site_file(slug, path)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    media_type, _ = mimetypes.guess_type(str(resolved))
    return FileResponse(resolved, media_type=media_type or "application/octet-stream")
