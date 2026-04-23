"""GeoNames plugin — Pydantic schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

UriFormat = Literal["web", "sws"]


class GeonamesHit(BaseModel):
    """One place-search result row surfaced to the editor panel."""

    model_config = ConfigDict(extra="forbid")

    # Numeric GeoNames id, e.g. "3171456" for Rome.
    geoname_id: str
    # Canonical URI built according to the plugin's url_format setting.
    # Either "https://www.geonames.org/{id}" (web, default) or
    # "http://sws.geonames.org/{id}/" (LOD semantic-web URI).
    uri: str
    # Display label: "Rome, Lazio, Italy" when region and country are
    # available; collapses gracefully for microstates or unnamed admin
    # divisions.
    display: str
    # Individual components, exposed so the UI can render a subtitle
    # separately from the main label without re-parsing the string.
    name: str
    region: str
    country: str
    # GeoNames "featureClass" (single char). Almost always "P"
    # (populated place) because that is what the default query filters
    # to, but surfaced in case a future config widens the filter.
    feature_class: str


class GeonamesConfig(BaseModel):
    """Read-model for the plugin's ``/config`` endpoint."""

    model_config = ConfigDict(extra="forbid")

    url_format: UriFormat
    # Non-editable snapshot of the shared username setting, purely so
    # the admin can see at a glance which account the plugin is using.
    geonames_username: str


class GeonamesConfigUpdate(BaseModel):
    """Write-model for the plugin's ``/config`` endpoint."""

    model_config = ConfigDict(extra="forbid")

    url_format: UriFormat | None = None
