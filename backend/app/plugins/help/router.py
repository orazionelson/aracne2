"""Help plugin — auth-only router.

All endpoints require any authenticated user. Assets are served directly
by the plugin (rather than by nginx) so the extension whitelist and
path-traversal checks live in one place.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.help.schemas import HelpPage, HelpSearchHit, HelpTreeNode
from app.plugins.help.service import (
    build_tree,
    get_asset,
    get_page,
    reset_cache,
    search,
)
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/help", tags=["help"])


@router.get("/tree")
async def help_tree(
    _: Annotated[User, Depends(require_role(min_role="User"))],
) -> DataResponse[list[HelpTreeNode]]:
    """Return the navigation tree derived from the help_docs directory."""
    return DataResponse(data=build_tree())


@router.get("/page")
async def help_page(
    _: Annotated[User, Depends(require_role(min_role="User"))],
    path: Annotated[str, Query(max_length=200)] = "",
) -> DataResponse[HelpPage]:
    """Return the rendered page at ``path`` (empty path → index.md)."""
    page = get_page(path)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Help page not found")
    return DataResponse(data=page)


@router.get("/search")
@limiter.limit("60/minute")
async def help_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> DataResponse[list[HelpSearchHit]]:
    """Full-text search across every help page, returning up to ``limit`` hits."""
    return DataResponse(data=search(q, limit=limit))


@router.post("/refresh")
async def help_refresh(
    _: Annotated[User, Depends(require_role(min_role="Admin"))],
) -> DataResponse[dict[str, bool]]:
    """Drop the in-process render cache so the next request re-parses.

    Not normally needed — the cache is mtime-fingerprinted — but useful
    after bulk-editing help files on the container filesystem.
    """
    reset_cache()
    return DataResponse(data={"ok": True})


@router.get("/assets/{path:path}")
async def help_asset(
    _: Annotated[User, Depends(require_role(min_role="User"))],
    path: str,
) -> FileResponse:
    """Serve whitelisted image files referenced by a rendered help page."""
    result = get_asset(path)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    file, content_type = result
    return FileResponse(file, media_type=content_type)
