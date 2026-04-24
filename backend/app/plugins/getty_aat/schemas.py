"""Getty AAT plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GettyAatHit(BaseModel):
    """One SPARQL result row surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    # Bare numeric AAT id, e.g. "300015050" for "oil paint".
    aat_id: str
    # Canonical URI used as @ref, e.g. "http://vocab.getty.edu/aat/300015050".
    # Getty uses HTTP (not HTTPS) as the persistent identifier scheme.
    uri: str
    # English preferred label.
    label: str
    # Scope note (short definition), if present. May be empty.
    scope_note: str
