from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import (
    EVENT_PLUGIN_ACTIVATED,
    EVENT_PLUGIN_DEACTIVATED,
    EVENT_PLUGIN_DELETED,
    emit_event,
)
from app.core.metrics import PLUGIN_LIFECYCLE
from app.core.plugin_loader import plugin_loader
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
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PluginResponse]:
    data = await activate_plugin(db, name)
    # Hot-mount the plugin's router on the running ASGI app so the
    # new endpoints start serving requests immediately — no backend
    # restart needed. Hook-only plugins (no router) silently no-op.
    plugin_loader.mount_plugin(request.app, name)
    PLUGIN_LIFECYCLE.labels(action="activated", plugin=name).inc()
    emit_event(
        EVENT_PLUGIN_ACTIVATED,
        plugin=name,
        actor_user_id=str(current_user.id),
    )
    return DataResponse(data=data)


@router.post("/{name}/deactivate")
async def plugin_deactivate(
    name: str,
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PluginResponse]:
    data = await deactivate_plugin(db, name)
    # Symmetric counterpart to activate: pop the plugin's routes off
    # the live FastAPI app so subsequent requests get a clean 404.
    plugin_loader.unmount_plugin(request.app, name)
    PLUGIN_LIFECYCLE.labels(action="deactivated", plugin=name).inc()
    emit_event(
        EVENT_PLUGIN_DEACTIVATED,
        plugin=name,
        actor_user_id=str(current_user.id),
    )
    return DataResponse(data=data)


@router.delete("/{name}", status_code=204)
async def plugin_delete(
    name: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_plugin(db, name)
    PLUGIN_LIFECYCLE.labels(action="deleted", plugin=name).inc()
    emit_event(
        EVENT_PLUGIN_DELETED,
        plugin=name,
        actor_user_id=str(current_user.id),
    )
