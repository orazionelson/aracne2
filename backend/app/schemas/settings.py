from datetime import datetime

from pydantic import BaseModel, field_validator


class SettingResponse(BaseModel):
    key: str
    value: str
    type: str
    description: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value cannot be empty")
        return v
