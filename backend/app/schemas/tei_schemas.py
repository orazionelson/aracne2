import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.tei_schema import SchemaFormat


class TeiSchemaCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()


class ImportUrl(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("url cannot be empty")
        return v.strip()


class TeiSchemaResponse(BaseModel):
    id: uuid.UUID
    name: str
    validation_filename: str | None
    validation_format: SchemaFormat | None
    cm5_filename: str | None
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationError(BaseModel):
    line: int
    col: int
    message: str
    path: str | None = None  # XPath location of the error node, when available


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError]
