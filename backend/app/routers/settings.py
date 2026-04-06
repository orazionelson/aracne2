from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.settings import SettingResponse, SettingUpdate
from app.services.settings import get_setting, list_settings, update_setting

router = APIRouter(prefix="/settings", tags=["settings"])

_admin = Depends(require_role(min_role="Admin"))


@router.get("")
async def settings_list(
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[SettingResponse]]:
    data = await list_settings(db)
    return DataResponse(data=data)


@router.get("/{key}")
async def setting_detail(
    key: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[SettingResponse]:
    data = await get_setting(db, key)
    return DataResponse(data=data)


@router.patch("/{key}")
async def setting_update(
    key: str,
    body: SettingUpdate,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[SettingResponse]:
    data = await update_setting(db, key, body, current_user)
    return DataResponse(data=data)
