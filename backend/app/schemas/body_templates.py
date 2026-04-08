import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class BodyTemplateCreate(BaseModel):
    label: str
    snippet: str

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("label cannot be empty")
        return v

    @field_validator("snippet")
    @classmethod
    def snippet_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("snippet cannot be empty")
        return v


class BodyTemplatePatch(BaseModel):
    label: str | None = None
    snippet: str | None = None

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("label cannot be empty")
        return v

    @field_validator("snippet")
    @classmethod
    def snippet_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("snippet cannot be empty")
        return v


class BodyTemplateResponse(BaseModel):
    id: uuid.UUID
    label: str
    snippet: str
    is_native: bool
    created_at: datetime

    model_config = {"from_attributes": True}
