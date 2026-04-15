import uuid
from datetime import datetime

from pydantic import BaseModel


class CollectionBibliographySave(BaseModel):
    content: str


class CollectionBibliographySetPublic(BaseModel):
    is_public: bool


class CollectionBibliographyResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    version: int
    content: str
    created_at: datetime
    created_by_id: uuid.UUID | None
    is_public: bool

    model_config = {"from_attributes": True}
