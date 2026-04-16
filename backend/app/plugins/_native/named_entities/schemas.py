"""Pydantic schemas for the Named Entity Index plugin."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class NamedEntityResponse(BaseModel):
    id: uuid.UUID
    type: str
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


class EntityTagConfig(BaseModel):
    """Full tag configuration payload for PUT /entities/admin/tag-config.

    *tags* is a list of TEI local element names to extract, e.g.
    ``["persName", "placeName", "orgName", "objectName"]``.
    The tag name is used directly as the entity type stored in the DB.
    Maximum 50 tags; each tag name must be ≤ 64 characters.
    """
    tags: list[str] = Field(..., min_length=1, max_length=50)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip() for t in v]
        if any(not t for t in cleaned):
            raise ValueError("Tag names cannot be empty")
        for tag in cleaned:
            if len(tag) > 64:
                raise ValueError("Tag names must be ≤ 64 characters")
        return cleaned
