import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.collection import CollectionStatus

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CollectionCreate(BaseModel):
    slug: str
    title: str
    description: str | None = None
    is_public: bool = False

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must contain only lowercase letters, digits and hyphens "
                "(e.g. 'dante-alighieri')"
            )
        if len(v) > 128:
            raise ValueError("slug must be 128 characters or fewer")
        return v

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title cannot be empty")
        return v


class CollectionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_public: bool | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("title cannot be empty")
        return v


class CollectionResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    status: CollectionStatus
    is_public: bool
    owner_id: uuid.UUID | None
    editor_id: uuid.UUID | None
    assigned_at: datetime | None
    submitted_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssignAction(BaseModel):
    user_id: uuid.UUID
    note: str | None = None


class WorkflowAction(BaseModel):
    note: str | None = None


class RejectAction(BaseModel):
    note: str
