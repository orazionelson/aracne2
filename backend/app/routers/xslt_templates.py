"""Router for the XSLT stylesheet catalog.

All endpoints are restricted to Designer+ (Designer, EditorInChief, Admin).
The list endpoint also serves the website Document tab so it returns
XsltTemplateSummary (no full content) for bandwidth efficiency.
The detail endpoint returns the full XsltTemplateResponse including content.
"""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
from app.db.postgres import get_async_session
from app.core.constants import ROLE_LEVEL
from app.middleware.acl import get_current_user
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.xslt_templates import (
    XsltTemplateCreate,
    XsltTemplatePatch,
    XsltTemplateResponse,
    XsltTemplateSummary,
)
from app.services.xslt_templates import (
    create_xslt_template,
    delete_xslt_template,
    get_xslt_template,
    list_xslt_templates,
    patch_xslt_template,
)

router = APIRouter(prefix="/xslt-templates", tags=["xslt-templates"])

_DEFAULT_XSLT_PATH = Path(__file__).parent.parent / "xslt" / "tei_generic.xsl"


async def _designer_plus(
    user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> User:
    """[D+] — Designer, EditorInChief, or Admin."""
    role: str = getattr(request.state, "role", "User")
    if role != "Designer" and ROLE_LEVEL.get(role, 0) < 3:
        raise AuthorizationError()
    return user


_D = Depends(_designer_plus)


@router.get("")
async def xslt_templates_list(
    current_user: Annotated[User, _D],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[XsltTemplateSummary]]:
    """Return all XSLT templates (summary — no content body)."""
    templates = await list_xslt_templates(db)
    return DataResponse(data=[XsltTemplateSummary.model_validate(t) for t in templates])


@router.get("/default/download")
async def xslt_template_default_download(
    current_user: Annotated[User, _D],
) -> FileResponse:
    """Download the built-in TEI→HTML stylesheet (tei_generic.xsl) as a file."""
    return FileResponse(
        path=str(_DEFAULT_XSLT_PATH),
        media_type="application/xml",
        filename="tei_generic.xsl",
    )


@router.get("/{template_id}")
async def xslt_template_detail(
    template_id: uuid.UUID,
    current_user: Annotated[User, _D],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[XsltTemplateResponse]:
    """Return a single XSLT template including the full stylesheet content."""
    tpl = await get_xslt_template(db, template_id)
    return DataResponse(data=XsltTemplateResponse.model_validate(tpl))


@router.post("", status_code=201)
async def xslt_template_create(
    payload: XsltTemplateCreate,
    current_user: Annotated[User, _D],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[XsltTemplateResponse]:
    tpl = await create_xslt_template(db, payload, created_by=current_user.id)
    await db.commit()
    return DataResponse(data=XsltTemplateResponse.model_validate(tpl))


@router.patch("/{template_id}")
async def xslt_template_patch(
    template_id: uuid.UUID,
    payload: XsltTemplatePatch,
    current_user: Annotated[User, _D],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[XsltTemplateResponse]:
    tpl = await patch_xslt_template(db, template_id, payload)
    await db.commit()
    return DataResponse(data=XsltTemplateResponse.model_validate(tpl))


@router.delete("/{template_id}", status_code=204)
async def xslt_template_delete(
    template_id: uuid.UUID,
    current_user: Annotated[User, _D],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await delete_xslt_template(db, template_id)
    await db.commit()
