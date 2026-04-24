"""CERL Thesaurus plugin — Pydantic schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# CERL's "type" field maps to one of these buckets — kept coarse for
# the editor UI's enclosing-tag validation.
EntityKind = Literal["person", "corporate", "place", "imprint", "other"]


class CerlHit(BaseModel):
    """One CERL Thesaurus result row surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    # CERL internal id, e.g. "cnp01283953" (persons), "cnl00007170"
    # (places), "cni00011234" (institutions / imprints).
    cerl_id: str
    # Canonical URI used as @ref, e.g. "https://data.cerl.org/thesaurus/cnp01283953".
    uri: str
    # Display label — the heading name.
    label: str
    # Disambiguating detail (dates, variant names, place).
    detail: str
    # Coarse category bucket for the editor UI.
    kind: EntityKind
