"""public_view router — unauthenticated public browsing endpoints.

All routes in this router require no authentication.  They expose only
published, is_public=True collections.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.schemas.common import DataResponse
from app.schemas.public_view import PublicCollectionDetail
from app.services.public_view import get_public_collection_detail, render_document_html

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/collections/{slug}")
async def public_collection_detail(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PublicCollectionDetail]:
    """Return metadata and document list for a published public collection."""
    data = await get_public_collection_detail(db, slug)
    return DataResponse(data=data)


@router.get("/collections/{slug}/documents/{filename}", response_class=HTMLResponse)
async def public_document_render(
    slug: str,
    filename: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> HTMLResponse:
    """Render a document to HTML via the built-in TEI XSLT stylesheet.

    Returns text/html directly so the frontend can embed it in an <iframe>.
    No authentication required — the collection must be published and public.
    """
    html = await render_document_html(db, slug, filename)
    return HTMLResponse(content=html)
