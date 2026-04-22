"""Pydantic schemas for the Wikidata search proxy."""

from pydantic import BaseModel


class WikidataHit(BaseModel):
    """One entity returned by the Wikidata search API.

    The ``uri`` field is the canonical entity URI (the ``concepturi`` returned
    by Wikidata). It is the value we persist as ``@ref`` on TEI entities —
    never reconstruct it from the QID client-side.
    """

    qid: str
    label: str
    description: str | None = None
    uri: str
