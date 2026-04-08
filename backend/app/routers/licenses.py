import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.licenses import LicenseCreate, LicensePatch, LicenseResponse
from app.services.licenses import (
    create_license,
    delete_license,
    list_licenses,
    patch_license,
)

router = APIRouter(prefix="/licenses", tags=["licenses"])

_admin = Depends(require_role(min_role="Admin"))
_auth = Depends(require_role(min_role="User"))


@router.get("")
async def licenses_list(
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[LicenseResponse]]:
    """Return all licenses. Available to every authenticated user."""
    data = await list_licenses(db)
    return DataResponse(data=data)


@router.post("", status_code=201)
async def license_create(
    payload: LicenseCreate,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[LicenseResponse]:
    lic = await create_license(db, payload)
    await db.commit()
    return DataResponse(data=lic)


@router.patch("/{license_id}")
async def license_patch(
    license_id: uuid.UUID,
    payload: LicensePatch,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[LicenseResponse]:
    lic = await patch_license(db, license_id, payload)
    await db.commit()
    return DataResponse(data=lic)


@router.delete("/{license_id}", status_code=204)
async def license_delete(
    license_id: uuid.UUID,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_license(db, license_id)
    await db.commit()
