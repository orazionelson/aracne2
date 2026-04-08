import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class LicenseCreate(BaseModel):
    name: str
    target: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("target")
    @classmethod
    def target_strip(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            return v or None
        return None


class LicensePatch(BaseModel):
    name: str | None = None
    target: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name must not be empty")
        return v

    @field_validator("target")
    @classmethod
    def target_strip(cls, v: str | None) -> str | None:
        if v is not None:
            return v.strip() or None
        return None


class LicenseResponse(BaseModel):
    id: uuid.UUID
    name: str
    target: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
