"""Schemas for the CrossRef lookup plugin — lookup response + config."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    """Response body for ``GET /plugins/crossref-lookup/lookup``."""

    model_config = ConfigDict(extra="forbid")

    xml_id: str
    biblstruct_xml: str
    preview: BiblStructPreview


class CrossrefLookupConfigResponse(BaseModel):
    """Plugin-level config surface — just the polite-pool contact email.

    ``fallback_email`` is informational: when ``contact_email`` is empty,
    the router falls back to the platform's ``admin_email`` so a fresh
    activation already identifies the operator correctly. The admin UI
    displays this fallback so the editor knows what ends up on the wire.
    """

    model_config = ConfigDict(extra="forbid")

    contact_email: str
    fallback_email: str


class CrossrefLookupConfigUpdate(BaseModel):
    """Partial update — empty string clears the override."""

    model_config = ConfigDict(extra="forbid")

    contact_email: str | None = Field(default=None, max_length=254)

    @field_validator("contact_email")
    @classmethod
    def email_or_empty(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if cleaned == "":
            return ""
        # Light shape check — reject values that clearly are not emails;
        # full RFC 5322 validation is not worth the dependency here.
        if "@" not in cleaned or "." not in cleaned.split("@", 1)[-1]:
            raise ValueError("contact_email must be an email address or empty")
        return cleaned
