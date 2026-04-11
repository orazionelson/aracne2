"""Pydantic schemas for document media (images associated with TEI documents)."""

from pydantic import BaseModel


class MediaItem(BaseModel):
    """A single image file in a document's media directory."""

    filename: str
    url: str
    size: int
    content_type: str


class MediaListResponse(BaseModel):
    """Response for the media list endpoint."""

    data: list[MediaItem]
