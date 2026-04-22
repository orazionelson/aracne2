"""Unit tests for mapping.py — pure, no DB, no network."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.plugins.zenodo_deposit.mapping import (
    Creator,
    DepositMetadata,
    collection_to_metadata,
    to_zenodo_payload,
    zenodo_license_slug,
)


def _mk_col(**overrides: Any) -> SimpleNamespace:
    """Build a lightweight Collection-shaped object.

    We do not instantiate the real SQLAlchemy model here: mapping.py only
    reads attributes, so a SimpleNamespace is enough and keeps the test
    free of DB setup.
    """
    defaults = dict(
        id=uuid.uuid4(),
        slug="divina-commedia",
        title="Divina Commedia",
        description=None,
        author=None,
        publisher=None,
        pub_year=None,
        published_at=None,
        license_id=None,
        resp_stmts=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _mk_license(target: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="Test license", target=target)


# ── zenodo_license_slug ─────────────────────────────────────────────────────


def test_license_slug_maps_known_cc_urls() -> None:
    assert zenodo_license_slug("https://creativecommons.org/licenses/by/4.0/") == "cc-by-4.0"
    assert zenodo_license_slug("https://creativecommons.org/publicdomain/zero/1.0/") == "cc-zero"
    assert (
        zenodo_license_slug("https://creativecommons.org/licenses/by-sa/4.0/")
        == "cc-by-sa-4.0"
    )


def test_license_slug_tolerates_missing_trailing_slash() -> None:
    # Our seed has trailing slashes; the mapper should also accept URLs
    # saved without one (admins can edit license rows).
    assert zenodo_license_slug("https://creativecommons.org/licenses/by/4.0") == "cc-by-4.0"


def test_license_slug_returns_none_for_unknown() -> None:
    assert zenodo_license_slug(None) is None
    assert zenodo_license_slug("") is None
    assert zenodo_license_slug("https://example.org/license") is None


# ── collection_to_metadata ──────────────────────────────────────────────────


def test_collection_to_metadata_uses_published_at_for_date() -> None:
    col = _mk_col(published_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC), pub_year=2020)
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    assert meta.publication_date.isoformat() == "2026-03-01"


def test_collection_to_metadata_falls_back_to_pub_year() -> None:
    col = _mk_col(published_at=None, pub_year=2020)
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    assert meta.publication_date.isoformat() == "2020-01-01"


def test_collection_to_metadata_builds_related_identifier_when_base_url_present() -> None:
    col = _mk_col(slug="dante-letters")
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url="https://edition.example.org",
        publication_type="other",
        access_right="open",
    )
    assert meta.related_identifier == "https://edition.example.org/browse/dante-letters"


def test_collection_to_metadata_strips_base_url_trailing_slash() -> None:
    col = _mk_col(slug="x")
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url="https://edition.example.org/",
        publication_type="other",
        access_right="open",
    )
    assert meta.related_identifier == "https://edition.example.org/browse/x"


def test_collection_to_metadata_omits_related_identifier_without_base_url() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(),
        license_obj=None,
        public_base_url="",
        publication_type="other",
        access_right="open",
    )
    assert meta.related_identifier is None


def test_collection_to_metadata_splits_authors_on_semicolon() -> None:
    col = _mk_col(author="Dante Alighieri; Giovanni Boccaccio")
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    names = [c.name for c in meta.creators]
    assert names == ["Dante Alighieri", "Giovanni Boccaccio"]


def test_collection_to_metadata_appends_resp_stmt_names_deduplicated() -> None:
    col = _mk_col(
        author="Dante Alighieri",
        resp_stmts=[
            {"resp": "edited by", "name": "M. Rossi"},
            {"resp": "edited by", "name": "Dante Alighieri"},  # duplicate
        ],
    )
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    assert [c.name for c in meta.creators] == ["Dante Alighieri", "M. Rossi"]


def test_collection_to_metadata_falls_back_to_anonymous_when_no_authors() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(author=None, resp_stmts=None, publisher=None),
        license_obj=None,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    assert len(meta.creators) == 1
    assert meta.creators[0].name == "Anonymous"


def test_collection_to_metadata_uses_publisher_when_no_authors() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(author=None, resp_stmts=None, publisher="Editore X"),
        license_obj=None,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    assert meta.creators[0].name == "Editore X"


def test_collection_to_metadata_maps_license_slug() -> None:
    lic = _mk_license("https://creativecommons.org/licenses/by/4.0/")
    meta = collection_to_metadata(
        collection=_mk_col(),
        license_obj=lic,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    assert meta.license_slug == "cc-by-4.0"


def test_collection_to_metadata_description_default() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(description=None, title="Test"),
        license_obj=None,
        public_base_url=None,
        publication_type="other",
        access_right="open",
    )
    assert "Test" in meta.description
    assert "Aracne2" in meta.description


# ── to_zenodo_payload ───────────────────────────────────────────────────────


def test_to_zenodo_payload_shape_happy_path() -> None:
    meta = DepositMetadata(
        title="Divina Commedia",
        description="An edition.",
        creators=[Creator(name="Dante Alighieri", orcid="0000-0000-0000-0001")],
        publication_date=datetime(2026, 4, 22, tzinfo=UTC).date(),
        keywords=["Dante"],
        license_slug="cc-by-4.0",
        access_right="open",
        publication_type="other",
        related_identifier="https://edition.example.org/browse/divina-commedia",
    )
    body = to_zenodo_payload(meta, community="humanities")
    assert body["metadata"]["upload_type"] == "publication"
    assert body["metadata"]["title"] == "Divina Commedia"
    assert body["metadata"]["creators"] == [
        {"name": "Dante Alighieri", "orcid": "0000-0000-0000-0001"}
    ]
    assert body["metadata"]["publication_date"] == "2026-04-22"
    assert body["metadata"]["keywords"] == ["Dante"]
    assert body["metadata"]["license"] == "cc-by-4.0"
    assert body["metadata"]["access_right"] == "open"
    assert body["metadata"]["related_identifiers"][0]["identifier"].endswith("divina-commedia")
    assert body["metadata"]["communities"] == [{"identifier": "humanities"}]


def test_to_zenodo_payload_omits_license_for_closed_access() -> None:
    meta = DepositMetadata(
        title="Closed record",
        description="x",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        access_right="closed",
        license_slug="cc-by-4.0",  # should NOT appear in output
    )
    body = to_zenodo_payload(meta)
    assert "license" not in body["metadata"]


def test_to_zenodo_payload_omits_keywords_when_empty() -> None:
    meta = DepositMetadata(
        title="x",
        description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
    )
    body = to_zenodo_payload(meta)
    assert "keywords" not in body["metadata"]


def test_to_zenodo_payload_drops_community_when_unset() -> None:
    meta = DepositMetadata(
        title="x",
        description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
    )
    body = to_zenodo_payload(meta, community=None)
    assert "communities" not in body["metadata"]
