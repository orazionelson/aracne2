"""Pure-unit tests for the Dataverse metadata serialiser.

Asserts the shape Dataverse's Native API expects without touching
the DB or the network.
"""

from __future__ import annotations

from datetime import date

from app.plugins.dataverse_integration.mapping import (
    Creator,
    DepositMetadata,
    to_dataverse_payload,
)


def _meta(**overrides) -> DepositMetadata:  # type: ignore[no-untyped-def]
    base = dict(
        title="Divina Commedia",
        description="A digital edition.",
        creators=[Creator(name="Dante Alighieri")],
        publication_date=date(2026, 4, 24),
        keywords=["medieval italian"],
        license_id=None,
        access="open",
        resource_type="publication-other",
        related_identifier="https://edition.example.org/browse/dante",
        publisher="Editor X",
    )
    base.update(overrides)
    return DepositMetadata(**base)


def _fields(payload: dict) -> dict[str, dict]:
    """Pull the ``fields`` array out of the citation block keyed on typeName."""
    citation = payload["datasetVersion"]["metadataBlocks"]["citation"]["fields"]
    return {f["typeName"]: f for f in citation}


def test_payload_carries_required_fields() -> None:
    payload = to_dataverse_payload(
        _meta(),
        subject="Arts and Humanities",
        contact_name="Plat Form",
        contact_email="curator@example.org",
    )
    fields = _fields(payload)
    # Dataverse's required-field set for the citation block.
    for required in ("title", "author", "datasetContact", "dsDescription", "subject"):
        assert required in fields, f"missing required field: {required}"


def test_subject_is_controlled_vocabulary_list() -> None:
    payload = to_dataverse_payload(
        _meta(),
        subject="Arts and Humanities",
        contact_name="x", contact_email="a@b.org",
    )
    subject = _fields(payload)["subject"]
    assert subject["typeClass"] == "controlledVocabulary"
    assert subject["value"] == ["Arts and Humanities"]


def test_author_field_emits_orcid_when_present() -> None:
    payload = to_dataverse_payload(
        _meta(creators=[
            Creator(name="Jane Doe", orcid="0000-0000-0000-0001"),
        ]),
        subject="Arts and Humanities",
        contact_name="x", contact_email="a@b.org",
    )
    author = _fields(payload)["author"]
    entry = author["value"][0]
    assert entry["authorName"]["value"] == "Jane Doe"
    assert entry["authorIdentifierScheme"]["value"] == "ORCID"
    assert entry["authorIdentifier"]["value"] == "0000-0000-0000-0001"


def test_dataset_contact_uses_email_and_optional_name() -> None:
    payload = to_dataverse_payload(
        _meta(),
        subject="x",
        contact_name="Plat Form",
        contact_email="curator@example.org",
    )
    contact = _fields(payload)["datasetContact"]
    entry = contact["value"][0]
    assert entry["datasetContactEmail"]["value"] == "curator@example.org"
    assert entry["datasetContactName"]["value"] == "Plat Form"


def test_dataset_contact_omits_name_when_empty() -> None:
    payload = to_dataverse_payload(
        _meta(),
        subject="x",
        contact_name="",  # admin didn't fill the name field
        contact_email="curator@example.org",
    )
    contact = _fields(payload)["datasetContact"]
    entry = contact["value"][0]
    assert "datasetContactName" not in entry
    assert entry["datasetContactEmail"]["value"] == "curator@example.org"


def test_keywords_are_compound_entries() -> None:
    payload = to_dataverse_payload(
        _meta(keywords=["a", "b"]),
        subject="x", contact_name="x", contact_email="a@b.org",
    )
    kw = _fields(payload)["keyword"]
    assert kw["typeClass"] == "compound"
    values = [e["keywordValue"]["value"] for e in kw["value"]]
    assert values == ["a", "b"]


def test_related_identifier_lands_in_notes_text() -> None:
    payload = to_dataverse_payload(
        _meta(related_identifier="https://edition.example.org/browse/x"),
        subject="x", contact_name="x", contact_email="a@b.org",
    )
    notes = _fields(payload)["notesText"]
    assert "https://edition.example.org/browse/x" in notes["value"]


def test_no_related_identifier_omits_notes_text() -> None:
    payload = to_dataverse_payload(
        _meta(related_identifier=None),
        subject="x", contact_name="x", contact_email="a@b.org",
    )
    assert "notesText" not in _fields(payload)
