import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.collection_validation_run import ValidationRunStatus


class CollectionValidationRunResponse(BaseModel):
    id: int
    collection_id: uuid.UUID
    started_by: uuid.UUID | None
    schema_id: uuid.UUID | None
    status: ValidationRunStatus
    doc_count: int
    validated_count: int
    error_count: int
    results: dict[str, Any] | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
