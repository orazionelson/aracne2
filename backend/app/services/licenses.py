import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.license import License
from app.schemas.licenses import LicenseCreate, LicensePatch


async def list_licenses(db: AsyncSession) -> list[License]:
    result = await db.execute(select(License).order_by(License.name))
    return list(result.scalars().all())


async def create_license(db: AsyncSession, payload: LicenseCreate) -> License:
    lic = License(name=payload.name, target=payload.target)
    db.add(lic)
    await db.flush()
    await db.refresh(lic)
    return lic


async def patch_license(
    db: AsyncSession, license_id: uuid.UUID, payload: LicensePatch
) -> License:
    lic = await db.get(License, license_id)
    if lic is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("License not found")
    if payload.name is not None:
        lic.name = payload.name
    if payload.target is not None or "target" in payload.model_fields_set:
        lic.target = payload.target
    if payload.is_active is not None:
        lic.is_active = payload.is_active
    await db.flush()
    await db.refresh(lic)
    return lic


async def delete_license(db: AsyncSession, license_id: uuid.UUID) -> None:
    lic = await db.get(License, license_id)
    if lic is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("License not found")
    await db.delete(lic)
    await db.flush()
