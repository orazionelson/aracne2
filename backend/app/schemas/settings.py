from datetime import datetime

from pydantic import BaseModel, field_validator


class SettingResponse(BaseModel):
    key: str
    value: str
    type: str
    description: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class UiConfigResponse(BaseModel):
    platform_name: str
    platform_logo_url: str
    navbar_bg_color: str


class LogoUploadResponse(BaseModel):
    url: str


class SettingUpdate(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value cannot be empty")
        return v
