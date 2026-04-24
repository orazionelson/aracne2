"""OpenAlex plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OpenAlexPreview(BaseModel):
    """Lightweight preview shown in the UI result list."""

    model_config = ConfigDict(extra="forbid")

    title: str
    authors: list[str] = []
    year: int | None = None
    type: str | None = None         # TEI-mapped (journalArticle / book / …)
    container: str | None = None    # journal / book series name
    publisher: str | None = None
    doi: str | None = None          # bare DOI (no URL prefix)
    openalex_id: str                # bare Wxxxxxxxxxx id
    uri: str                        # canonical OpenAlex URL


class OpenAlexHit(BaseModel):
    """One search result — preview + ready-to-insert TEI XML."""

    model_config = ConfigDict(extra="forbid")

    xml_id: str                # ``bib_surname_year``
    biblstruct_xml: str        # full ``<biblStruct>…</biblStruct>``
    preview: OpenAlexPreview


class OpenAlexConfig(BaseModel):
    """Read-model for ``/config``."""

    model_config = ConfigDict(extra="forbid")

    contact_email: str
    fallback_email: str   # platform admin_email, shown as fallback hint


class OpenAlexConfigUpdate(BaseModel):
    """Write-model for ``/config``."""

    model_config = ConfigDict(extra="forbid")

    contact_email: str | None = None
