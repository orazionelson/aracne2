"""CRUD service for the XSLT stylesheet catalog."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.xslt_template import XsltTemplate
from app.schemas.xslt_templates import XsltTemplateCreate, XsltTemplatePatch


async def list_xslt_templates(db: AsyncSession) -> list[XsltTemplate]:
    result = await db.execute(select(XsltTemplate).order_by(XsltTemplate.name))
    return list(result.scalars().all())


async def get_xslt_template(db: AsyncSession, template_id: uuid.UUID) -> XsltTemplate:
    tpl = await db.get(XsltTemplate, template_id)
    if tpl is None:
        raise NotFoundError("XSLT template not found")
    return tpl


async def create_xslt_template(
    db: AsyncSession,
    payload: XsltTemplateCreate,
    created_by: uuid.UUID | None = None,
) -> XsltTemplate:
    existing = await db.scalar(
        select(XsltTemplate).where(XsltTemplate.name == payload.name)
    )
    if existing is not None:
        raise ConflictError("An XSLT template with this name already exists")
    tpl = XsltTemplate(
        name=payload.name,
        description=payload.description,
        content=payload.content,
        processor=payload.processor,
        tags=payload.tags,
        created_by=created_by,
    )
    db.add(tpl)
    await db.flush()
    await db.refresh(tpl)
    return tpl


async def patch_xslt_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    payload: XsltTemplatePatch,
) -> XsltTemplate:
    tpl = await db.get(XsltTemplate, template_id)
    if tpl is None:
        raise NotFoundError("XSLT template not found")
    if payload.name is not None:
        clash = await db.scalar(
            select(XsltTemplate).where(
                XsltTemplate.name == payload.name,
                XsltTemplate.id != template_id,
            )
        )
        if clash is not None:
            raise ConflictError("An XSLT template with this name already exists")
        tpl.name = payload.name
    if payload.description is not None:
        tpl.description = payload.description
    if payload.content is not None:
        tpl.content = payload.content
    if payload.processor is not None:
        tpl.processor = payload.processor
    if payload.tags is not None:
        tpl.tags = payload.tags
    await db.flush()
    await db.refresh(tpl)
    return tpl


async def delete_xslt_template(db: AsyncSession, template_id: uuid.UUID) -> None:
    tpl = await db.get(XsltTemplate, template_id)
    if tpl is None:
        raise NotFoundError("XSLT template not found")
    await db.delete(tpl)
    await db.flush()
