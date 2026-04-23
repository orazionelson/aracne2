"""Schemas for the bibliography router — CrossRef DOI resolver response."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BiblStructPreview(BaseModel):
    """Human-readable projection of the resolved biblStruct.

    Shown in the UI before the editor commits the fragment to the
    document; keeps the frontend free of XML parsing.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    authors: list[str] = []
    year: int | None = None
    container: str | None = None
    publisher: str | None = None
    doi: str | None = None
    type: str | None = None


class CrossrefLookupResponse(BaseModel):
    """Response body for ``GET /bibliography/crossref``."""

    model_config = ConfigDict(extra="forbid")

    xml_id: str
    biblstruct_xml: str
    preview: BiblStructPreview
