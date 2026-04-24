"""Trismegistos plugin — Pydantic schemas.

Trismegistos does not publish a free-text search API. Every public
Trismegistos data service is an **ID resolver**: you hand it a TM
numeric ID (or, for texts, a partner-project ID + a ``source``
selector), and it returns either cross-references to other
databases or a ``Message: not in our database`` envelope.

The plugin therefore exposes a single ``resolve`` call. The panel's
UX is "paste an ID, pick the source" — not "type a name".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# TM entity types. Persons are purely a URL-composition: TM does not
# expose a JSON endpoint for persons (only RDF/XML), so the plugin
# validates the ID and constructs the canonical URL without hitting
# the network.
TmKind = Literal["person", "place", "text"]

# Partner-project sources accepted by ``texrelations``. Only the
# whitelisted set is allowed through to TM to avoid echoing arbitrary
# user input into the URL. Always keep ``trismegistos`` first — it is
# the default for a direct TM ID lookup.
TmTextSource = Literal[
    "trismegistos",
    "ddbdp",
    "hgv",
    "phi",
    "edh",
    "edcs",
    "edr",
    "edb",
    "isic",
    "rib",
    "lupa",
    "pn",
    "ba",
    "he",
    "uoxf",
]


class TrismegistosHit(BaseModel):
    """Resolved TM record, ready to apply as ``@ref``.

    ``partners`` is the cross-reference map returned by
    ``texrelations`` / ``georelations``. Keys are partner-DB names
    (e.g. ``HGV``, ``DDBDP``, ``Wikipedia``); values are the list of
    IDs that point to the same record in that DB. Empty for persons
    (no JSON API).
    """

    model_config = ConfigDict(extra="forbid")

    tm_id: str
    uri: str
    label: str
    kind: TmKind
    partners: dict[str, list[str]]


class TrismegistosResolveRequest(BaseModel):
    """Body of ``POST /plugins/trismegistos/resolve``."""

    model_config = ConfigDict(extra="forbid")

    kind: TmKind
    identifier: str = Field(min_length=1, max_length=200)
    # Only meaningful when ``kind == "text"``; ignored otherwise.
    source: TmTextSource = "trismegistos"
