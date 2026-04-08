import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.body_templates import (
    BodyTemplateCreate,
    BodyTemplatePatch,
    BodyTemplateResponse,
)
from app.schemas.common import DataResponse
from app.services.body_templates import (
    create_body_template,
    delete_body_template,
    list_body_templates,
    patch_body_template,
)

router = APIRouter(prefix="/body-templates", tags=["body-templates"])

_admin = Depends(require_role(min_role="Admin"))
_auth = Depends(require_role(min_role="User"))


@router.get("")
async def body_templates_list(
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[BodyTemplateResponse]]:
    """Return all body templates. Available to every authenticated user."""
    data = await list_body_templates(db)
    return DataResponse(data=data)


@router.post("", status_code=201)
async def body_template_create(
    payload: BodyTemplateCreate,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[BodyTemplateResponse]:
    tpl = await create_body_template(db, payload)
    await db.commit()
    return DataResponse(data=tpl)


@router.patch("/{template_id}")
async def body_template_patch(
    template_id: uuid.UUID,
    payload: BodyTemplatePatch,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[BodyTemplateResponse]:
    tpl = await patch_body_template(db, template_id, payload)
    await db.commit()
    return DataResponse(data=tpl)


@router.delete("/{template_id}", status_code=204)
async def body_template_delete(
    template_id: uuid.UUID,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_body_template(db, template_id)
    await db.commit()
