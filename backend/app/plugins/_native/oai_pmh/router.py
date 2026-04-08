"""OAI-PMH Provider — public endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.plugins._native.oai_pmh import service

router = APIRouter(prefix="/oai", tags=["oai-pmh"])

_DbDep = Annotated[AsyncSession, Depends(get_async_session)]
_ExistDep = Annotated[ExistDBClient, Depends(get_existdb)]


@router.get("")
async def oai_endpoint(
    request: Request,
    db: _DbDep,
    existdb: _ExistDep,
    verb: Annotated[str | None, Query()] = None,
    identifier: Annotated[str | None, Query()] = None,
    metadata_prefix: Annotated[str | None, Query(alias="metadataPrefix")] = None,
    set_spec: Annotated[str | None, Query(alias="set")] = None,
    from_date: Annotated[str | None, Query(alias="from")] = None,
    until: Annotated[str | None, Query()] = None,
    resumption_token: Annotated[str | None, Query(alias="resumptionToken")] = None,
) -> Response:
    """OAI-PMH 2.0 data provider.

    All verbs are handled through the ``verb`` query parameter as per the
    OAI-PMH protocol specification. No authentication required — this endpoint
    is intentionally public.

    Example requests:
      GET /api/v1/oai?verb=Identify
      GET /api/v1/oai?verb=ListSets
      GET /api/v1/oai?verb=ListMetadataFormats
      GET /api/v1/oai?verb=ListIdentifiers&metadataPrefix=oai_dc
      GET /api/v1/oai?verb=ListRecords&metadataPrefix=oai_dc
      GET /api/v1/oai?verb=GetRecord&identifier=oai:host:slug/file.xml&metadataPrefix=oai_dc
    """
    base_url = str(request.url).split("?")[0]
    xml_body = await service.dispatch(
        base_url=base_url,
        verb=verb,
        identifier=identifier,
        metadata_prefix=metadata_prefix,
        set_spec=set_spec,
        from_date=from_date,
        until=until,
        resumption_token=resumption_token,
        db=db,
        existdb=existdb,
    )
    return Response(content=xml_body, media_type="application/xml; charset=UTF-8")
