from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.plugins import PluginResponse
from app.services.plugins import (
    activate_plugin,
    deactivate_plugin,
    delete_plugin,
    list_plugins,
)

router = APIRouter(prefix="/plugins", tags=["plugins"])

_admin = Depends(require_role(min_role="Admin"))


@router.get("")
async def plugins_list(
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[PluginResponse]]:
    data = await list_plugins(db)
    return DataResponse(data=data)


@router.post("/{name}/activate")
async def plugin_activate(
    name: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PluginResponse]:
    data = await activate_plugin(db, name)
    return DataResponse(data=data)


@router.post("/{name}/deactivate")
async def plugin_deactivate(
    name: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PluginResponse]:
    data = await deactivate_plugin(db, name)
    return DataResponse(data=data)


@router.delete("/{name}", status_code=204)
async def plugin_delete(
    name: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_plugin(db, name)
