"""ROR plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RorHit(BaseModel):
    """One search result row surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    # Bare ROR id, e.g. "03vek6s52".
    ror_id: str
    # Canonical URI, e.g. "https://ror.org/03vek6s52".
    uri: str
    # Display label — the name flagged as ror_display when available.
    name: str
    # Other names and labels (aliases, acronyms, localised labels).
    aliases: list[str] = []
    # Human-readable country name, for disambiguation in the hit list.
    country: str | None = None
    # ROR types: education, facility, healthcare, company, archive,
    # nonprofit, government, other.
    types: list[str] = []
