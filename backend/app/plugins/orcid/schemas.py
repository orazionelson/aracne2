"""ORCID plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OrcidHit(BaseModel):
    """One search result row surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    orcid: str           # bare identifier, e.g. "0000-0002-1825-0097"
    uri: str             # canonical URI, e.g. "https://orcid.org/0000-..."
    given_names: str | None = None
    family_name: str | None = None
    credit_name: str | None = None          # preferred display name when set
    affiliations: list[str] = []            # institution names, if any

    @property
    def label(self) -> str:
        """One-line display name for the UI — preferred > given+family > ORCID."""
        if self.credit_name and self.credit_name.strip():
            return self.credit_name.strip()
        parts = [s for s in (self.given_names, self.family_name) if s and s.strip()]
        if parts:
            return " ".join(p.strip() for p in parts)
        return self.orcid
