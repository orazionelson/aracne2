"""Public endpoints for the search engine embed widget.

This router is mounted on a separate FastAPI sub-app (in main.py) that has its
own CORSMiddleware configured to allow all origins for preflight.  Actual origin
enforcement (whitelist check) is performed inside each route handler by the
embed service, which also writes an embed log entry on every request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.services.embed import (
    advanced_search_embed,
    render_widget_js,
    search_embed,
)

router = APIRouter()

_MAX_RESULTS_DEFAULT = 50
_MAX_RESULTS_LIMIT = 200


@router.get("/{slug}/widget.js")
async def widget_js(
    slug: str,
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    """Serve the self-contained JS widget for the given search engine.

    The file is dynamically generated from the engine's embed_config.
    Cached by CDN / browser for 5 minutes (Cache-Control: max-age=300).
    """
    js = await render_widget_js(db, slug)
    return Response(
        content=js,
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "max-age=300, public"},
    )


@router.get("/{slug}/search")
async def embed_search(
    slug: str,
    request: Request,
    q: str = Query(..., min_length=1, max_length=512),
    collections: str | None = Query(
        None, description="Comma-separated collection slugs"
    ),
    max_results: int = Query(
        default=_MAX_RESULTS_DEFAULT, ge=1, le=_MAX_RESULTS_LIMIT
    ),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Full-text search via the embed widget.

    Origin is checked against the engine's allowed_origins whitelist.
    Every request (allowed or blocked) is logged in search_engine_embed_logs.
    """
    col_list = [s.strip() for s in collections.split(",") if s.strip()] if collections else None
    result = await search_embed(db, slug, q, col_list, max_results, request)
    return {"data": result.model_dump()}


@router.get("/{slug}/advanced-search")
async def embed_advanced_search(
    slug: str,
    request: Request,
    q: str | None = Query(None, max_length=512),
    element: str | None = Query(
        None,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9._-]*$",
    ),
    attr_name: str | None = Query(
        None,
        max_length=64,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9._-]*$",
    ),
    attr_value: str | None = Query(None, max_length=256),
    collections: str | None = Query(
        None, description="Comma-separated collection slugs"
    ),
    max_results: int = Query(
        default=_MAX_RESULTS_DEFAULT, ge=1, le=_MAX_RESULTS_LIMIT
    ),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Advanced structural/attribute search via the embed widget.

    Origin is checked against the engine's allowed_origins whitelist.
    Every request (allowed or blocked) is logged in search_engine_embed_logs.
    """
    col_list = [s.strip() for s in collections.split(",") if s.strip()] if collections else None
    result = await advanced_search_embed(
        db, slug, q, element, attr_name, attr_value, col_list, max_results, request
    )
    return {"data": result.model_dump()}
