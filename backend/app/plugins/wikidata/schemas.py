"""Wikidata plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WikidataHit(BaseModel):
    """One entity returned by the Wikidata search API.

    The ``uri`` field is the canonical entity URI (the ``concepturi``
    returned by Wikidata). It is the value we persist as ``@ref`` on
    TEI entities — never reconstruct it from the QID client-side.
    """

    model_config = ConfigDict(extra="forbid")

    qid: str
    label: str
    description: str | None = None
    uri: str
