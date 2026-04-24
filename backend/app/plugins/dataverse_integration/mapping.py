"""Collection / Website → Dataverse dataset metadata.

Reuses the service-agnostic ``DepositMetadata`` intermediate already
produced by the Zenodo plugin (it was deliberately decoupled from
the InvenioRDM serialiser for exactly this reuse). The Dataverse-
specific work is the ``to_dataverse_payload`` serialiser at the
bottom of this module — it shapes ``DepositMetadata`` plus a few
Dataverse-required fields (subject, dataset contact) into the
nested ``datasetVersion.metadataBlocks.citation.fields`` payload
the Native API expects.

Reference: https://guides.dataverse.org/en/latest/api/native-api.html
"""

from __future__ import annotations

from typing import Any

from app.plugins.zenodo_deposit.mapping import (  # noqa: F401 — re-exported
    Creator,
    DepositMetadata,
    collection_to_metadata,
    split_name,
    website_to_metadata,
)


# ── Dataverse "citation" metadata block serialiser ────────────────────────
#
# Every primitive field follows the shape:
#   {"typeName": "<name>", "multiple": <bool>, "typeClass": "primitive",
#    "value": "<scalar>"}
# Compound fields wrap a list of dicts whose values are themselves
# primitive entries:
#   {"typeName": "author", "multiple": True, "typeClass": "compound",
#    "value": [{"authorName": {...}, "authorAffiliation": {...}}, ...]}
# Controlled-vocabulary lists carry "typeClass": "controlledVocabulary"
# with a list of strings as the value.


def _primitive(name: str, value: str, *, multiple: bool = False) -> dict[str, Any]:
    return {
        "typeName": name,
        "multiple": multiple,
        "typeClass": "primitive",
        "value": value,
    }


def _primitive_list(name: str, values: list[str]) -> dict[str, Any]:
    return {
        "typeName": name,
        "multiple": True,
        "typeClass": "primitive",
        "value": values,
    }


def _controlled_vocab(name: str, values: list[str]) -> dict[str, Any]:
    return {
        "typeName": name,
        "multiple": True,
        "typeClass": "controlledVocabulary",
        "value": values,
    }


def _author_field(creators: list[Creator]) -> dict[str, Any]:
    """Build the compound ``author`` field from our generic Creator list.

    Dataverse's author entry takes either a free-text full name OR
    given/family pair; we send the full name because Aracne2 stores
    authors as a single free-text string. Affiliation is included
    when present; ORCID rides on ``authorIdentifier`` +
    ``authorIdentifierScheme=ORCID`` per the Dataverse 5.x schema.
    """
    entries: list[dict[str, Any]] = []
    for c in creators:
        entry: dict[str, Any] = {
            "authorName": _primitive("authorName", c.name),
        }
        if c.affiliation:
            entry["authorAffiliation"] = _primitive(
                "authorAffiliation", c.affiliation,
            )
        if c.orcid:
            entry["authorIdentifierScheme"] = {
                "typeName": "authorIdentifierScheme",
                "multiple": False,
                "typeClass": "controlledVocabulary",
                "value": "ORCID",
            }
            entry["authorIdentifier"] = _primitive(
                "authorIdentifier", c.orcid,
            )
        entries.append(entry)
    return {
        "typeName": "author",
        "multiple": True,
        "typeClass": "compound",
        "value": entries,
    }


def _dataset_contact_field(name: str, email: str) -> dict[str, Any]:
    """Build the compound ``datasetContact`` field (required).

    A single contact entry is enough for our editorial use case —
    multiple contacts are supported by the API but rarely useful for
    a derived edition deposit.
    """
    entry: dict[str, Any] = {
        "datasetContactEmail": _primitive("datasetContactEmail", email),
    }
    if name:
        entry["datasetContactName"] = _primitive("datasetContactName", name)
    return {
        "typeName": "datasetContact",
        "multiple": True,
        "typeClass": "compound",
        "value": [entry],
    }


def _description_field(text: str) -> dict[str, Any]:
    """Build the compound ``dsDescription`` field (required)."""
    return {
        "typeName": "dsDescription",
        "multiple": True,
        "typeClass": "compound",
        "value": [{
            "dsDescriptionValue": _primitive("dsDescriptionValue", text),
        }],
    }


def _related_url_note(url: str) -> dict[str, Any]:
    """Optional second description carrying the canonical Aracne2 URL.

    Dataverse's "notesText" primitive is the conventional slot for an
    informal note; we use it to point at the source page so a curator
    can verify the deposit derives from a live edition.
    """
    return _primitive(
        "notesText",
        f"Source: {url}",
    )


def to_dataverse_payload(
    meta: DepositMetadata,
    *,
    subject: str,
    contact_name: str,
    contact_email: str,
) -> dict[str, Any]:
    """Serialise our generic DepositMetadata into the Dataverse Native
    API dataset payload.

    All four arguments are required by Dataverse's citation metadata
    block — the plugin config defaults the subject to "Arts and
    Humanities" and the contact to the platform's admin email when
    the per-deposit values are not overridden.
    """
    fields: list[dict[str, Any]] = [
        _primitive("title", meta.title),
        _author_field(meta.creators),
        _dataset_contact_field(contact_name, contact_email),
        _description_field(meta.description),
        _controlled_vocab("subject", [subject]),
    ]

    if meta.publisher:
        fields.append(_primitive("producer", meta.publisher))

    if meta.keywords:
        fields.append({
            "typeName": "keyword",
            "multiple": True,
            "typeClass": "compound",
            "value": [
                {"keywordValue": _primitive("keywordValue", k)}
                for k in meta.keywords
            ],
        })

    if meta.related_identifier:
        fields.append(_related_url_note(meta.related_identifier))

    fields.append(_primitive(
        "distributionDate",
        meta.publication_date.isoformat(),
    ))

    return {
        "datasetVersion": {
            "metadataBlocks": {
                "citation": {
                    "displayName": "Citation Metadata",
                    "fields": fields,
                },
            },
        },
    }
