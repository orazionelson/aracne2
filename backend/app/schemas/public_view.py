"""public_view — Pydantic schemas for unauthenticated public browsing."""

from pydantic import BaseModel


class PublicDocumentInfo(BaseModel):
    filename: str
    title: str | None
    author: str | None


class PublicCollectionDetail(BaseModel):
    slug: str
    title: str
    description: str | None
    author: str | None
    publisher: str | None
    pub_year: int | None
    documents: list[PublicDocumentInfo]
