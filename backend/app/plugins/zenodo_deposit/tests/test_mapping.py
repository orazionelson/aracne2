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
    split_name,
    to_zenodo_payload,
    zenodo_license_id,
)


def _mk_col(**overrides: Any) -> SimpleNamespace:
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


# ── zenodo_license_id ───────────────────────────────────────────────────────


def test_license_id_maps_known_cc_urls() -> None:
    assert zenodo_license_id("https://creativecommons.org/licenses/by/4.0/") == "cc-by-4.0"
    assert zenodo_license_id("https://creativecommons.org/publicdomain/zero/1.0/") == "cc0-1.0"
    assert (
        zenodo_license_id("https://creativecommons.org/licenses/by-sa/4.0/")
        == "cc-by-sa-4.0"
    )


def test_license_id_tolerates_missing_trailing_slash() -> None:
    assert zenodo_license_id("https://creativecommons.org/licenses/by/4.0") == "cc-by-4.0"


def test_license_id_returns_none_for_unknown() -> None:
    assert zenodo_license_id(None) is None
    assert zenodo_license_id("") is None
    assert zenodo_license_id("https://example.org/license") is None


# ── split_name ──────────────────────────────────────────────────────────────


def test_split_name_comma_style() -> None:
    assert split_name("Alighieri, Dante") == ("Dante", "Alighieri")


def test_split_name_space_style() -> None:
    assert split_name("Dante Alighieri") == ("Dante", "Alighieri")


def test_split_name_handles_middle_names() -> None:
    assert split_name("Johann Wolfgang Goethe") == ("Johann Wolfgang", "Goethe")


def test_split_name_single_token_becomes_family() -> None:
    # InvenioRDM requires family_name; single-token names are surfaced as
    # family so Zenodo still accepts them.
    assert split_name("Homer") == ("", "Homer")


def test_split_name_empty_returns_empties() -> None:
    assert split_name("") == ("", "")
    assert split_name("   ") == ("", "")


# ── collection_to_metadata ──────────────────────────────────────────────────


def test_collection_to_metadata_uses_published_at_for_date() -> None:
    col = _mk_col(published_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC), pub_year=2020)
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    assert meta.publication_date.isoformat() == "2026-03-01"


def test_collection_to_metadata_falls_back_to_pub_year() -> None:
    col = _mk_col(published_at=None, pub_year=2020)
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    assert meta.publication_date.isoformat() == "2020-01-01"


def test_collection_to_metadata_builds_related_identifier_when_base_url_present() -> None:
    col = _mk_col(slug="dante-letters")
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url="https://edition.example.org",
        resource_type="publication-other",
        access="open",
    )
    assert meta.related_identifier == "https://edition.example.org/browse/dante-letters"


def test_collection_to_metadata_strips_base_url_trailing_slash() -> None:
    col = _mk_col(slug="x")
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url="https://edition.example.org/",
        resource_type="publication-other",
        access="open",
    )
    assert meta.related_identifier == "https://edition.example.org/browse/x"


def test_collection_to_metadata_omits_related_identifier_without_base_url() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(),
        license_obj=None,
        public_base_url="",
        resource_type="publication-other",
        access="open",
    )
    assert meta.related_identifier is None


def test_collection_to_metadata_splits_authors_on_semicolon() -> None:
    col = _mk_col(author="Dante Alighieri; Giovanni Boccaccio")
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    names = [c.name for c in meta.creators]
    assert names == ["Dante Alighieri", "Giovanni Boccaccio"]


def test_collection_to_metadata_appends_resp_stmt_names_deduplicated() -> None:
    col = _mk_col(
        author="Dante Alighieri",
        resp_stmts=[
            {"resp": "edited by", "name": "M. Rossi"},
            {"resp": "edited by", "name": "Dante Alighieri"},
        ],
    )
    meta = collection_to_metadata(
        collection=col,
        license_obj=None,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    assert [c.name for c in meta.creators] == ["Dante Alighieri", "M. Rossi"]


def test_collection_to_metadata_falls_back_to_anonymous_when_no_authors() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(author=None, resp_stmts=None, publisher=None),
        license_obj=None,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    assert len(meta.creators) == 1
    assert meta.creators[0].name == "Anonymous"


def test_collection_to_metadata_uses_publisher_when_no_authors() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(author=None, resp_stmts=None, publisher="Editore X"),
        license_obj=None,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    assert meta.creators[0].name == "Editore X"


def test_collection_to_metadata_maps_license_id() -> None:
    lic = _mk_license("https://creativecommons.org/licenses/by/4.0/")
    meta = collection_to_metadata(
        collection=_mk_col(),
        license_obj=lic,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    assert meta.license_id == "cc-by-4.0"


def test_collection_to_metadata_description_default() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(description=None, title="Test"),
        license_obj=None,
        public_base_url=None,
        resource_type="publication-other",
        access="open",
    )
    assert "Test" in meta.description
    assert "Aracne2" in meta.description


def test_collection_to_metadata_propagates_resource_type_and_access() -> None:
    meta = collection_to_metadata(
        collection=_mk_col(),
        license_obj=None,
        public_base_url=None,
        resource_type="publication-book",
        access="restricted",
    )
    assert meta.resource_type == "publication-book"
    assert meta.access == "restricted"


# ── to_zenodo_payload (InvenioRDM shape) ────────────────────────────────────


def test_payload_has_inveniordm_top_level_keys() -> None:
    meta = DepositMetadata(
        title="Divina Commedia",
        description="An edition.",
        creators=[Creator(name="Dante Alighieri")],
        publication_date=datetime(2026, 4, 22, tzinfo=UTC).date(),
    )
    body = to_zenodo_payload(meta)
    assert set(body.keys()) == {"access", "files", "metadata"}
    assert body["files"] == {"enabled": True}


def test_payload_access_open_is_public_public() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        access="open",
    )
    body = to_zenodo_payload(meta)
    assert body["access"] == {"record": "public", "files": "public"}


def test_payload_access_restricted_is_restricted_restricted() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        access="restricted",
    )
    body = to_zenodo_payload(meta)
    assert body["access"] == {"record": "restricted", "files": "restricted"}


def test_payload_resource_type_is_wrapped_as_id_object() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        resource_type="publication-book",
    )
    body = to_zenodo_payload(meta)
    assert body["metadata"]["resource_type"] == {"id": "publication-book"}


def test_payload_creator_splits_name_into_personal_shape() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        creators=[Creator(name="Dante Alighieri", orcid="0000-0000-0000-0001")],
    )
    body = to_zenodo_payload(meta)
    creators = body["metadata"]["creators"]
    assert creators == [
        {
            "person_or_org": {
                "type": "personal",
                "family_name": "Alighieri",
                "given_name": "Dante",
                "identifiers": [
                    {"scheme": "orcid", "identifier": "0000-0000-0000-0001"}
                ],
            }
        }
    ]


def test_payload_creator_with_affiliation() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        creators=[Creator(name="M. Rossi", affiliation="University of Pisa")],
    )
    body = to_zenodo_payload(meta)
    assert body["metadata"]["creators"][0]["affiliations"] == [
        {"name": "University of Pisa"}
    ]


def test_payload_creator_with_single_token_name_has_family_only() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        creators=[Creator(name="Homer")],
    )
    body = to_zenodo_payload(meta)
    person = body["metadata"]["creators"][0]["person_or_org"]
    assert person["family_name"] == "Homer"
    assert "given_name" not in person


def test_payload_rights_emitted_for_open_access_only() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        license_id="cc-by-4.0",
        access="open",
    )
    body = to_zenodo_payload(meta)
    assert body["metadata"]["rights"] == [{"id": "cc-by-4.0"}]


def test_payload_rights_omitted_for_restricted_access() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        license_id="cc-by-4.0",
        access="restricted",
    )
    body = to_zenodo_payload(meta)
    assert "rights" not in body["metadata"]


def test_payload_related_identifier_uses_inveniordm_shape() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        related_identifier="https://edition.example.org/browse/divina-commedia",
    )
    body = to_zenodo_payload(meta)
    assert body["metadata"]["related_identifiers"] == [
        {
            "identifier": "https://edition.example.org/browse/divina-commedia",
            "scheme": "url",
            "relation_type": {"id": "isalternateidentifierof"},
            "resource_type": {"id": "publication-other"},
        }
    ]


def test_payload_subjects_from_keywords() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        keywords=["Dante", "Manoscritti"],
    )
    body = to_zenodo_payload(meta)
    assert body["metadata"]["subjects"] == [
        {"subject": "Dante"},
        {"subject": "Manoscritti"},
    ]


def test_payload_omits_optional_blocks_when_empty() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
    )
    body = to_zenodo_payload(meta)
    md = body["metadata"]
    assert "publisher" not in md
    assert "subjects" not in md
    assert "rights" not in md
    assert "related_identifiers" not in md


def test_payload_publisher_emitted_when_set() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        publisher="Aracne2",
    )
    body = to_zenodo_payload(meta)
    assert body["metadata"]["publisher"] == "Aracne2"


def test_payload_publication_date_is_isoformat() -> None:
    meta = DepositMetadata(
        title="x", description="y",
        publication_date=datetime(2026, 4, 22, tzinfo=UTC).date(),
    )
    body = to_zenodo_payload(meta)
    assert body["metadata"]["publication_date"] == "2026-04-22"
