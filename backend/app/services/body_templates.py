import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_template import BodyTemplate
from app.schemas.body_templates import BodyTemplateCreate, BodyTemplatePatch


async def list_body_templates(db: AsyncSession) -> list[BodyTemplate]:
    result = await db.execute(select(BodyTemplate).order_by(BodyTemplate.label))
    return list(result.scalars().all())


async def create_body_template(
    db: AsyncSession, payload: BodyTemplateCreate
) -> BodyTemplate:
    tpl = BodyTemplate(label=payload.label, snippet=payload.snippet)
    db.add(tpl)
    await db.flush()
    await db.refresh(tpl)
    return tpl


async def patch_body_template(
    db: AsyncSession, template_id: uuid.UUID, payload: BodyTemplatePatch
) -> BodyTemplate:
    tpl = await db.get(BodyTemplate, template_id)
    if tpl is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Body template not found")
    if payload.label is not None:
        tpl.label = payload.label
    if payload.snippet is not None:
        tpl.snippet = payload.snippet
    await db.flush()
    await db.refresh(tpl)
    return tpl


async def delete_body_template(db: AsyncSession, template_id: uuid.UUID) -> None:
    tpl = await db.get(BodyTemplate, template_id)
    if tpl is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Body template not found")
    await db.delete(tpl)
    await db.flush()
