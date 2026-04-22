"""Collection → Zenodo deposit metadata.

Design note: the intermediate ``DepositMetadata`` is deliberately
service-agnostic.  A future DataCite or HAL plugin can reuse the same
shape and plug a different serialiser — the service-specific layer is
the ``to_zenodo_payload`` function, not the extraction from the ORM.

Keep this module pure (no DB, no I/O, no framework imports beyond
stdlib / dataclasses) so it is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.models.collection import Collection
from app.models.license import License


# --- Creative Commons → Zenodo SPDX slug map -----------------------------------
#
# Zenodo accepts a ``license`` string on the deposition metadata in SPDX-ish
# shape (e.g. "cc-by-4.0").  Our ``licenses`` table does not carry an SPDX
# column, so we match on the `target` URL which we seed deterministically in
# ``db/seed.py`` (DEFAULT_LICENSES).  If the user has renamed the license or
# replaced the target URL, the lookup falls back to None and the payload
# omits the ``license`` field — Zenodo then defaults to "cc-zero".
_CC_LICENSE_MAP: dict[str, str] = {
    "https://creativecommons.org/publicdomain/zero/1.0/": "cc-zero",
    "https://creativecommons.org/licenses/by/4.0/": "cc-by-4.0",
    "https://creativecommons.org/licenses/by-sa/4.0/": "cc-by-sa-4.0",
    "https://creativecommons.org/licenses/by-nc/4.0/": "cc-by-nc-4.0",
    "https://creativecommons.org/licenses/by-nc-sa/4.0/": "cc-by-nc-sa-4.0",
    "https://creativecommons.org/licenses/by-nd/4.0/": "cc-by-nd-4.0",
    "https://creativecommons.org/licenses/by-nc-nd/4.0/": "cc-by-nc-nd-4.0",
}


def zenodo_license_slug(license_target: str | None) -> str | None:
    """Return the Zenodo license slug for a known CC URL, else None."""
    if not license_target:
        return None
    return _CC_LICENSE_MAP.get(license_target.rstrip("/") + "/") or _CC_LICENSE_MAP.get(
        license_target
    )


# --- Reusable intermediate shape ----------------------------------------------


@dataclass
class Creator:
    """A deposit creator (author / contributor).

    The optional ``orcid`` string is accepted as a bare ORCID identifier
    (``0000-0000-0000-0000``) and left to the serialiser to format.
    """

    name: str
    orcid: str | None = None
    affiliation: str | None = None


@dataclass
class DepositMetadata:
    """Service-agnostic description of a deposit.

    Every field is populated from platform data that already exists
    (Collection + License).  The Zenodo serialiser consumes this dataclass
    and produces the exact JSON payload Zenodo expects; a sibling DataCite
    serialiser can consume the same dataclass without extra extraction.
    """

    title: str
    description: str
    creators: list[Creator] = field(default_factory=list)
    publication_date: date = field(default_factory=lambda: datetime.now(UTC).date())
    keywords: list[str] = field(default_factory=list)
    license_slug: str | None = None
    access_right: str = "open"
    publication_type: str = "other"
    related_identifier: str | None = None  # canonical public URL on Aracne2
    publisher: str | None = None


def _split_authors(raw: str | None) -> list[str]:
    """Split a free-text author field into individual names.

    Accepts comma-separated ("Smith, J., Doe, J.") or semicolon-separated
    ("Smith, J.; Doe, J.") inputs.  Returns the list with whitespace
    stripped and empty entries removed.
    """
    if not raw:
        return []
    # Prefer ';' when present — it is less ambiguous than ',' with "Surname, Name"
    # formatting.  Falls back to ',' for the classic comma-separated case.
    separator = ";" if ";" in raw else ","
    return [name.strip() for name in raw.split(separator) if name.strip()]


def _resp_stmt_names(resp_stmts: list[dict[str, Any]] | None) -> list[str]:
    """Extract TEI respStmt names as a flat list, preserving order.

    Each entry in ``resp_stmts`` is ``{"resp": "...", "name": "..."}``.
    We only care about the name for Zenodo — the responsibility phrase
    (editor / curator / …) is not surfaced in the deposit metadata.
    """
    if not resp_stmts:
        return []
    names: list[str] = []
    for entry in resp_stmts:
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def collection_to_metadata(
    *,
    collection: Collection,
    license_obj: License | None,
    public_base_url: str | None,
    publication_type: str,
    access_right: str,
) -> DepositMetadata:
    """Build a DepositMetadata from a Collection and its License.

    ``public_base_url`` is the platform's canonical public origin
    (``https://edition.example.org``).  When empty we simply omit the
    related identifier — Zenodo accepts a deposit without it.
    """
    authors: list[str] = _split_authors(collection.author)
    resp_names: list[str] = _resp_stmt_names(collection.resp_stmts)
    # The primary author goes first; respStmt contributors follow as
    # additional creators.  This mirrors how a TEI edition is typically cited.
    creator_names: list[str] = list(dict.fromkeys(authors + resp_names))
    creators = [Creator(name=n) for n in creator_names] or [
        Creator(name=collection.publisher or "Anonymous")
    ]

    pub_date: date
    if collection.published_at is not None:
        pub_date = collection.published_at.date()
    elif collection.pub_year is not None:
        pub_date = date(collection.pub_year, 1, 1)
    else:
        pub_date = datetime.now(UTC).date()

    related_identifier: str | None = None
    if public_base_url:
        related_identifier = f"{public_base_url.rstrip('/')}/browse/{collection.slug}"

    license_slug = zenodo_license_slug(license_obj.target if license_obj else None)

    description = (
        collection.description
        or f"Collection “{collection.title}” published via Aracne2."
    )

    keywords: list[str] = []
    if collection.publisher:
        keywords.append(collection.publisher)

    return DepositMetadata(
        title=collection.title,
        description=description,
        creators=creators,
        publication_date=pub_date,
        keywords=keywords,
        license_slug=license_slug,
        access_right=access_right,
        publication_type=publication_type,
        related_identifier=related_identifier,
        publisher=collection.publisher,
    )


# --- Zenodo-specific serialiser ------------------------------------------------


def to_zenodo_payload(
    meta: DepositMetadata,
    *,
    community: str | None = None,
) -> dict[str, Any]:
    """Serialise DepositMetadata into the JSON body Zenodo expects.

    Reference: https://developers.zenodo.org/#representation
    We intentionally populate only the fields Zenodo accepts unconditionally;
    the deposit API tolerates unknown keys but we do not rely on it.
    """
    creators_payload: list[dict[str, str]] = []
    for c in meta.creators:
        entry: dict[str, str] = {"name": c.name}
        if c.orcid:
            entry["orcid"] = c.orcid
        if c.affiliation:
            entry["affiliation"] = c.affiliation
        creators_payload.append(entry)

    body: dict[str, Any] = {
        "upload_type": "publication",
        "publication_type": meta.publication_type,
        "title": meta.title,
        "description": meta.description,
        "creators": creators_payload,
        "publication_date": meta.publication_date.isoformat(),
        "access_right": meta.access_right,
    }
    if meta.keywords:
        body["keywords"] = list(meta.keywords)
    if meta.license_slug and meta.access_right in {"open", "embargoed"}:
        # Zenodo rejects 'license' for closed / restricted deposits.
        body["license"] = meta.license_slug
    if meta.related_identifier:
        body["related_identifiers"] = [
            {
                "identifier": meta.related_identifier,
                "relation": "isAlternateIdentifier",
                "resource_type": "publication-other",
            }
        ]
    if community:
        body["communities"] = [{"identifier": community}]

    return {"metadata": body}
