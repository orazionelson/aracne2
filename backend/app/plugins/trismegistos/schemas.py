"""Trismegistos plugin — Pydantic schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# TM entity types. ``person`` covers TM People, ``place`` covers
# TM Places, ``text`` covers TM Texts (the papyrus / ostracon / …
# records themselves).
TmKind = Literal["person", "place", "text"]


class TrismegistosHit(BaseModel):
    """One TM result surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    # Numeric TM id.
    tm_id: str
    # Canonical URI used as @ref, e.g. "https://www.trismegistos.org/person/12345".
    uri: str
    # Display label (best available name).
    label: str
    # Disambiguating detail (dates, provenance, genre, …). May be empty.
    detail: str
    # Entity kind bucket.
    kind: TmKind


class TrismegistosConfig(BaseModel):
    """Read-model for ``/config``. The raw API key is never returned —
    only a boolean ``key_set`` flag, same pattern as
    ``zenodo_deposit``."""

    model_config = ConfigDict(extra="forbid")

    api_key_set: bool
    # A short hint the UI uses to explain why the plugin will not
    # work until an API key is provided.
    registration_url: str = "https://www.trismegistos.org/api"


class TrismegistosConfigUpdate(BaseModel):
    """Write-model for ``/config``. Sending ``""`` clears the key."""

    model_config = ConfigDict(extra="forbid")

    api_key: str | None = None
