"""GND plugin — Pydantic schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# Mapped down from lobid.org's "type" array, which carries multiple
# URIs (DifferentiatedPerson, Person, AuthorityResource, …). We pick
# the most specific match and collapse to one of these buckets so the
# editor UI can warn on mismatch (e.g. selecting a corporate body
# while authoring <persName>).
EntityKind = Literal["person", "corporate", "place", "work", "subject", "other"]


class GndHit(BaseModel):
    """One search result row surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    # Bare GND numeric id, e.g. "118524534" for Goethe.
    gnd_id: str
    # Canonical GND URI used as @ref, e.g. "https://d-nb.info/gnd/118524534".
    # Preferred over the lobid.org URL because it is the persistent
    # identifier issued by the DNB.
    uri: str
    # Display label — preferredName from lobid.org.
    label: str
    # Additional disambiguating text (biographical dates, profession,
    # coordinates for places). May be empty.
    detail: str
    # Category bucket for UI filtering / target-tag validation.
    kind: EntityKind
