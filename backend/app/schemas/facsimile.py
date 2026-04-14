"""Pydantic v2 schemas for TEI <zone> text-image alignment."""

from pydantic import BaseModel, field_validator


class ZoneIn(BaseModel):
    """A single zone submitted by the client.

    Coordinates are pixel values relative to the original (full-resolution) image.
    The ``xml_id`` field carries the bare XML id value — the '#' prefix used in
    ``facs`` attribute references must NOT be included here.
    """

    xml_id: str
    ulx: int
    uly: int
    lrx: int
    lry: int

    @field_validator("xml_id")
    @classmethod
    def id_no_hash(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("xml_id cannot be empty")
        if v.startswith("#"):
            raise ValueError("xml_id must not include the '#' prefix")
        return v


class ZoneOut(BaseModel):
    """A zone as returned by the API."""

    xml_id: str
    ulx: int
    uly: int
    lrx: int
    lry: int


class ZoneUpdateRequest(BaseModel):
    """Full replacement of all zones for one surface (PUT semantics).

    Sending an empty list removes all existing zones.
    """

    zones: list[ZoneIn]


class SurfaceZonesResponse(BaseModel):
    """Response envelope wrapping the zone list for a surface."""

    surface_id: str
    zones: list[ZoneOut]
