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
    public_home_enabled: bool
    home_show_collections: bool
    home_show_search: bool
    home_show_login_button: bool
    has_custom_homepage_css: bool
    home_propagate_css: bool
    evt_enabled: bool


class LogoUploadResponse(BaseModel):
    url: str


class HomepageCssUploadResponse(BaseModel):
    url: str


class SettingUpdate(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value cannot be empty")
        return v
