"""Collection → Zenodo (InvenioRDM) deposit metadata.

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
from app.models.website import Website


# --- Creative Commons → InvenioRDM rights vocabulary id map --------------------
#
# The new Zenodo API accepts a ``rights`` array whose entries reference
# InvenioRDM's licenses vocabulary (``GET /api/vocabularies/licenses``). The
# SPDX-style ids below match the default seeded values in that vocabulary —
# they are stable and documented. If the user replaces a seeded license's
# target URL we fall back to no ``rights`` entry (the deposit still works,
# but Zenodo will flag the record as missing a license).
_CC_LICENSE_MAP: dict[str, str] = {
    "https://creativecommons.org/publicdomain/zero/1.0/": "cc0-1.0",
    "https://creativecommons.org/licenses/by/4.0/": "cc-by-4.0",
    "https://creativecommons.org/licenses/by-sa/4.0/": "cc-by-sa-4.0",
    "https://creativecommons.org/licenses/by-nc/4.0/": "cc-by-nc-4.0",
    "https://creativecommons.org/licenses/by-nc-sa/4.0/": "cc-by-nc-sa-4.0",
    "https://creativecommons.org/licenses/by-nd/4.0/": "cc-by-nd-4.0",
    "https://creativecommons.org/licenses/by-nc-nd/4.0/": "cc-by-nc-nd-4.0",
}


def zenodo_license_id(license_target: str | None) -> str | None:
    """Return the InvenioRDM license vocabulary id for a CC URL, else None."""
    if not license_target:
        return None
    canonical = license_target.rstrip("/") + "/"
    return _CC_LICENSE_MAP.get(canonical) or _CC_LICENSE_MAP.get(license_target)


# --- Reusable intermediate shape ----------------------------------------------


@dataclass
class Creator:
    """A deposit creator (author / contributor).

    ``name`` is a free-text full name; the Zenodo serialiser will split it
    into given/family-name using :func:`split_name`. An optional ``orcid``
    is accepted as a bare ORCID id (``0000-0000-0000-0000``) and emitted
    as a ``person_or_org.identifiers`` entry.
    """

    name: str
    orcid: str | None = None
    affiliation: str | None = None


@dataclass
class DepositMetadata:
    """Service-agnostic description of a deposit.

    Populated by :func:`collection_to_metadata` from Collection + License.
    Consumed by :func:`to_zenodo_payload`; a sibling DataCite serialiser
    can consume the same dataclass without extra extraction.
    """

    title: str
    description: str
    creators: list[Creator] = field(default_factory=list)
    publication_date: date = field(default_factory=lambda: datetime.now(UTC).date())
    keywords: list[str] = field(default_factory=list)
    license_id: str | None = None
    # Simplified to two values — "open" → public record+files, "restricted"
    # → both restricted. InvenioRDM also supports "embargoed" with a date,
    # but that requires UI we do not ship in the MVP.
    access: str = "open"
    # InvenioRDM resource-type vocabulary id (e.g. "publication-book",
    # "image-photo", "dataset"). Defaults to "publication-other" for
    # TEI editions which have no perfect match in the default vocabulary.
    resource_type: str = "publication-other"
    related_identifier: str | None = None  # canonical public URL on Aracne2
    publisher: str | None = None


def _split_authors(raw: str | None) -> list[str]:
    """Split a free-text author field into individual names."""
    if not raw:
        return []
    separator = ";" if ";" in raw else ","
    return [name.strip() for name in raw.split(separator) if name.strip()]


def _resp_stmt_names(resp_stmts: list[dict[str, Any]] | None) -> list[str]:
    """Extract TEI respStmt names as a flat list, preserving order."""
    if not resp_stmts:
        return []
    names: list[str] = []
    for entry in resp_stmts:
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def split_name(raw: str) -> tuple[str, str]:
    """Heuristic split of a free-text name into ``(given, family)``.

    InvenioRDM's personal-creator schema requires ``family_name``. Since
    Aracne2 stores authors as a single free-text string we split by the
    two most common conventions:

    * ``"Last, First"``  →  ``(first.strip(), last.strip())``
    * ``"First Middle Last"``  →  ``(first_middle, last)``

    Single-token names are emitted as ``("", name)`` — the full string
    becomes the family name, given name is empty. Zenodo accepts this.
    """
    raw = raw.strip()
    if not raw:
        return "", ""
    if "," in raw:
        last, first = raw.split(",", 1)
        return first.strip(), last.strip()
    tokens = raw.split()
    if len(tokens) < 2:
        return "", raw
    return " ".join(tokens[:-1]), tokens[-1]


def collection_to_metadata(
    *,
    collection: Collection,
    license_obj: License | None,
    public_base_url: str | None,
    resource_type: str,
    access: str,
    orcid_by_name: dict[str, str] | None = None,
) -> DepositMetadata:
    """Build a DepositMetadata from a Collection and its License.

    ``orcid_by_name`` is an optional case-insensitive map from author
    name (free-text, as it appears in Collection.author / resp_stmts)
    to an ORCID identifier. Any Creator whose name matches a key gets
    its ``orcid`` field populated — downstream the Zenodo payload
    carries it under ``creator.identifiers`` and the LOD graph under
    ``schema:sameAs``. The map is built by the caller from the User
    table (there is no in-collection ORCID storage).
    """
    authors: list[str] = _split_authors(collection.author)
    resp_names: list[str] = _resp_stmt_names(collection.resp_stmts)
    creator_names: list[str] = list(dict.fromkeys(authors + resp_names))
    orcid_map = {k.casefold(): v for k, v in (orcid_by_name or {}).items()}
    creators = [
        Creator(name=n, orcid=orcid_map.get(n.casefold())) for n in creator_names
    ] or [
        Creator(
            name=collection.publisher or "Anonymous",
            orcid=orcid_map.get((collection.publisher or "").casefold()),
        )
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

    license_id = zenodo_license_id(license_obj.target if license_obj else None)

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
        license_id=license_id,
        access=access,
        resource_type=resource_type,
        related_identifier=related_identifier,
        publisher=collection.publisher,
    )


def website_to_metadata(
    *,
    website: Website,
    source_collection: Collection | None,
    license_obj: License | None,
    public_base_url: str | None,
    resource_type: str,
    access: str,
    orcid_by_name: dict[str, str] | None = None,
) -> DepositMetadata:
    """Build a :class:`DepositMetadata` from a Website.

    A website is always *derivative* of a collection — its rendered
    output (HTML/CSS/JS/JSON) is generated from the collection's TEI
    files plus a theme. So the deposit shape mirrors the collection's
    where possible:

      - ``title`` / ``description`` come from the website itself,
        falling back to the source collection.
      - ``creators`` come from the source collection (its authors and
        respStmts), since the rendered files don't carry their own
        author metadata. With no collection, fall back to the
        configured ``publisher`` or "Anonymous".
      - ``related_identifier`` points at the public URL of the
        Aracne2-served version of the website (``public_base_url +
        '/sites/' + slug``) so Zenodo cross-links the snapshot.
      - ``resource_type`` defaults to the *website* default — not the
        collection's per-record override, which describes the source
        edition rather than the rendered site.
    """
    if source_collection is not None:
        creators = collection_to_metadata(
            collection=source_collection,
            license_obj=license_obj,
            public_base_url=public_base_url,
            resource_type=resource_type,
            access=access,
            orcid_by_name=orcid_by_name,
        ).creators
    else:
        publisher = getattr(website, "publisher", None) or "Anonymous"
        orcid_map = {
            k.casefold(): v for k, v in (orcid_by_name or {}).items()
        }
        creators = [
            Creator(
                name=publisher,
                orcid=orcid_map.get(publisher.casefold()),
            )
        ]

    title = website.title or (
        source_collection.title if source_collection else "Untitled website"
    )
    description = (
        (website.description or "").strip()
        or (
            source_collection.description
            if source_collection and source_collection.description
            else f"Rendered website “{title}” published via Aracne2."
        )
    )
    publisher = (
        getattr(website, "publisher", None)
        or (source_collection.publisher if source_collection else None)
    )

    pub_date: date
    if source_collection and source_collection.published_at is not None:
        pub_date = source_collection.published_at.date()
    else:
        pub_date = datetime.now(UTC).date()

    related_identifier: str | None = None
    if public_base_url:
        related_identifier = (
            f"{public_base_url.rstrip('/')}/sites/{website.slug}"
        )

    license_id = zenodo_license_id(license_obj.target if license_obj else None)

    keywords: list[str] = []
    if publisher:
        keywords.append(publisher)

    return DepositMetadata(
        title=title,
        description=description,
        creators=creators,
        publication_date=pub_date,
        keywords=keywords,
        license_id=license_id,
        access=access,
        resource_type=resource_type,
        related_identifier=related_identifier,
        publisher=publisher,
    )


# --- Zenodo-specific serialiser ------------------------------------------------


def _creator_to_inveniordm(c: Creator) -> dict[str, Any]:
    """Build one InvenioRDM creator entry from a free-text Creator."""
    given, family = split_name(c.name)
    person_or_org: dict[str, Any] = {
        "type": "personal",
        "family_name": family,
    }
    # InvenioRDM treats given_name as optional; omit when empty so the
    # payload does not carry a semantically wrong empty string.
    if given:
        person_or_org["given_name"] = given
    if c.orcid:
        person_or_org["identifiers"] = [
            {"scheme": "orcid", "identifier": c.orcid}
        ]
    entry: dict[str, Any] = {"person_or_org": person_or_org}
    if c.affiliation:
        entry["affiliations"] = [{"name": c.affiliation}]
    return entry


def to_zenodo_payload(
    meta: DepositMetadata,
    *,
    community: str | None = None,  # accepted for API parity; used post-publish
) -> dict[str, Any]:
    """Serialise DepositMetadata into the InvenioRDM records API body.

    Reference: https://inveniordm.docs.cern.ch/reference/metadata/

    Communities are attached post-publish via the review/submit flow, not
    inline on the record body, so the ``community`` argument is accepted
    for interface parity with the legacy implementation but not used here.
    Leaving the parameter in place keeps caller code stable for when we
    wire the community submit flow.
    """
    # Access block — InvenioRDM gate is split into "record visibility"
    # (who can see the landing page) and "files visibility" (who can
    # download). For the MVP we keep them aligned.
    access_is_public = meta.access == "open"
    body: dict[str, Any] = {
        "access": {
            "record": "public" if access_is_public else "restricted",
            "files": "public" if access_is_public else "restricted",
        },
        "files": {"enabled": True},
        "metadata": {
            "resource_type": {"id": meta.resource_type},
            "title": meta.title,
            "description": meta.description,
            "publication_date": meta.publication_date.isoformat(),
            "creators": [_creator_to_inveniordm(c) for c in meta.creators],
        },
    }

    if meta.publisher:
        body["metadata"]["publisher"] = meta.publisher

    if meta.keywords:
        body["metadata"]["subjects"] = [{"subject": k} for k in meta.keywords]

    # Licenses are only meaningful for access=public; restricted records
    # do not get a ``rights`` entry because the content is not
    # redistributable as-is.
    if meta.license_id and access_is_public:
        body["metadata"]["rights"] = [{"id": meta.license_id}]

    if meta.related_identifier:
        body["metadata"]["related_identifiers"] = [
            {
                "identifier": meta.related_identifier,
                "scheme": "url",
                "relation_type": {"id": "isalternateidentifierof"},
                "resource_type": {"id": "publication-other"},
            }
        ]

    # ``community`` intentionally unused here — see docstring.
    _ = community

    return body
