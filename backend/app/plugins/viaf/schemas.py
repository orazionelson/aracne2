"""VIAF plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ViafHit(BaseModel):
    """One AutoSuggest result row surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    # Bare numeric VIAF cluster id, e.g. "27063124" for Dante.
    viaf_id: str
    # Canonical URI, e.g. "http://viaf.org/viaf/27063124".
    # VIAF's own "permanent URL" uses HTTP (not HTTPS) per their docs.
    uri: str
    # Display label — the preferred name + dates, as VIAF formats it.
    display: str
    # "personal" (person) or "corporate" (organisation) — lets the
    # editor UI warn when the caller selected e.g. a corporate body
    # while authoring <persName>.
    name_type: str
