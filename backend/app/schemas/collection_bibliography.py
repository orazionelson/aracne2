import uuid
from datetime import datetime

from pydantic import BaseModel


class CollectionBibliographySave(BaseModel):
    content: str


class CollectionBibliographyResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    version: int
    content: str
    created_at: datetime
    created_by_id: uuid.UUID | None

    model_config = {"from_attributes": True}
