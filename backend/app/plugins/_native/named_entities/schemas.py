"""Pydantic schemas for the Named Entity Index plugin."""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.plugins._native.named_entities.models import EntityType


class NamedEntityResponse(BaseModel):
    id: uuid.UUID
    type: EntityType
    canonical_form: str
    authority_ref: str | None
    occurrence_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EntityOccurrenceResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    collection_id: uuid.UUID
    collection_slug: str
    collection_title: str
    filename: str
    raw_form: str
    context: str | None


class NamedEntityUpdate(BaseModel):
    canonical_form: str | None = None
    authority_ref: str | None = None

    @field_validator("canonical_form")
    @classmethod
    def canonical_form_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("canonical_form cannot be empty")
        return v.strip() if v else v


class EntityMergeRequest(BaseModel):
    """Merge source_id into target_id: all occurrences are reassigned, source is deleted."""
    source_id: uuid.UUID
    target_id: uuid.UUID
