"""Peripleo plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PeripleoHit(BaseModel):
    """One Peripleo search result surfaced to the editor panel.

    Peripleo aggregates heterogeneous gazetteers — each hit carries
    an ``id`` that is the canonical URI of the *source* gazetteer
    (Pleiades, iDAI, ChronOntology, …), not a Peripleo URI. That is
    the value we write as TEI ``@ref``.
    """

    model_config = ConfigDict(extra="forbid")

    # Canonical URI from the source gazetteer, e.g.
    # "https://pleiades.stoa.org/places/423025".
    uri: str
    # Display label (place name in the best available language).
    label: str
    # Source gazetteer name as surfaced by Peripleo: "Pleiades",
    # "iDAI.gazetteer", "ChronOntology", "ToposText", "Vici", …
    source: str
    # Short description: typically region + country, or historical
    # period, or type ("Roman settlement"). May be empty.
    detail: str
