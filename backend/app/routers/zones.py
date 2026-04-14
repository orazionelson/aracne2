"""TEI zone router — text-image alignment at word/line level.

Endpoints
---------
GET  /collections/{slug}/documents/{filename}/facsimile/{surface_id}/zones
    Return all <zone> elements for a surface.  [E+]
    Returns an empty list when no <facsimile> block exists.

PUT  /collections/{slug}/documents/{filename}/facsimile/{surface_id}/zones
    Replace all zones for a surface atomically.  [E+]
    Sending an empty list removes all existing zones.

POST /collections/{slug}/documents/{filename}/facsimile/{surface_id}/zones/import
    Import zones from an HTR pipeline (v1: same semantics as PUT).  [E+]
    Separate path reserved for future ALTO/PAGE XML format support.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.facsimile import SurfaceZonesResponse, ZoneUpdateRequest
from app.services.xmldb import get_surface_zones, update_surface_zones

router = APIRouter(prefix="/collections", tags=["zones"])

_auth = Depends(get_current_user)


@router.get("/{slug}/documents/{filename}/facsimile/{surface_id}/zones")
async def surface_zones_get(
    slug: str,
    filename: str,
    surface_id: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[SurfaceZonesResponse]:
    """Return all ``<zone>`` elements for a surface in a TEI document [E+].

    Returns an empty zone list when the document has no ``<facsimile>`` block.
    """
    role: str = request.state.role
    data = await get_surface_zones(db, existdb, slug, filename, surface_id, current_user, role)
    return DataResponse(data=data)


@router.put("/{slug}/documents/{filename}/facsimile/{surface_id}/zones")
async def surface_zones_update(
    slug: str,
    filename: str,
    surface_id: str,
    body: ZoneUpdateRequest,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[SurfaceZonesResponse]:
    """Replace all ``<zone>`` elements for a surface atomically [E+].

    Sending an empty ``zones`` list removes all existing zones.
    """
    role: str = request.state.role
    data = await update_surface_zones(
        db, existdb, slug, filename, surface_id, body.zones, current_user, role
    )
    return DataResponse(data=data)


@router.post(
    "/{slug}/documents/{filename}/facsimile/{surface_id}/zones/import",
    status_code=201,
)
async def surface_zones_import(
    slug: str,
    filename: str,
    surface_id: str,
    body: ZoneUpdateRequest,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[SurfaceZonesResponse]:
    """Import zones from an external HTR pipeline [E+].

    v1: identical semantics to ``PUT zones``.  The separate path enables future
    format evolution (e.g. accepting raw ALTO or PAGE XML) without breaking the
    manual editor path.
    """
    role: str = request.state.role
    data = await update_surface_zones(
        db, existdb, slug, filename, surface_id, body.zones, current_user, role
    )
    return DataResponse(data=data)
