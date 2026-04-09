"""Pydantic v2 schemas for the XSLT stylesheet catalog."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_VALID_PROCESSORS = {"lxml", "saxon"}


class XsltTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    content: str = Field(..., min_length=1)
    processor: str = "lxml"
    tags: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

    @field_validator("content")
    @classmethod
    def content_strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content cannot be blank")
        return v

    @field_validator("processor")
    @classmethod
    def processor_valid(cls, v: str) -> str:
        if v not in _VALID_PROCESSORS:
            raise ValueError(f"processor must be one of: {', '.join(_VALID_PROCESSORS)}")
        return v


class XsltTemplatePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    content: str | None = Field(None, min_length=1)
    processor: str | None = None
    tags: list[str] | None = None

    @field_validator("name")
    @classmethod
    def name_strip(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name cannot be blank")
        return v

    @field_validator("processor")
    @classmethod
    def processor_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_PROCESSORS:
            raise ValueError(f"processor must be one of: {', '.join(_VALID_PROCESSORS)}")
        return v


class XsltTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    content: str
    processor: str
    tags: list[str]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class XsltTemplateSummary(BaseModel):
    """Lightweight response for catalog listing (omits full content)."""
    id: uuid.UUID
    name: str
    description: str | None
    processor: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
