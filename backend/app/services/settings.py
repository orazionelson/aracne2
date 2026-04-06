from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.schemas.settings import SettingResponse, SettingUpdate


def _validate_value(key: str, value: str, type_: str) -> None:
    if type_ == "int":
        try:
            int(value)
        except ValueError:
            raise DomainValidationError(
                code="INVALID_SETTING_VALUE",
                message=f"Setting '{key}' requires an integer value",
            )
    elif type_ == "bool":
        if value not in ("true", "false"):
            raise DomainValidationError(
                code="INVALID_SETTING_VALUE",
                message=f"Setting '{key}' requires 'true' or 'false'",
            )


async def list_settings(db: AsyncSession) -> list[SettingResponse]:
    rows = await db.scalars(select(SystemSetting).order_by(SystemSetting.key))
    return [SettingResponse.model_validate(r) for r in rows]


async def get_setting(db: AsyncSession, key: str) -> SettingResponse:
    row = await db.get(SystemSetting, key)
    if not row:
        raise NotFoundError(f"Setting '{key}' not found")
    return SettingResponse.model_validate(row)


async def update_setting(
    db: AsyncSession, key: str, body: SettingUpdate, actor: User
) -> SettingResponse:
    row = await db.get(SystemSetting, key)
    if not row:
        raise NotFoundError(f"Setting '{key}' not found")
    _validate_value(key, body.value, row.type)
    row.value = body.value
    row.updated_by = actor.id
    row.updated_at = datetime.now(UTC)
    await db.flush()
    return SettingResponse.model_validate(row)
