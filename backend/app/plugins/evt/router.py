"""EVT viewer integration router — public endpoints for config and XML delivery."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.plugins.evt import service

router = APIRouter(prefix="/public/collections", tags=["evt"])


@router.get("/{slug}/evt-config")
async def evt_collection_config(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> JSONResponse:
    """Return EVT 2-compatible config.json for a public collection [pub].

    Consumed by the EVT nginx container via a proxy_pass rule.
    """
    config = await service.get_evt_config(db, existdb, slug)
    return JSONResponse(
        content=config,
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/{slug}/documents/{filename}/raw")
async def evt_document_raw(
    slug: str,
    filename: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> Response:
    """Return raw XML bytes for a document in a public collection [pub].

    Consumed by the EVT nginx container via a proxy_pass rule.
    """
    xml_bytes = await service.get_document_xml(db, existdb, slug, filename)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=300"},
    )
