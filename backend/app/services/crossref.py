"""CrossRef DOI resolver — fetches canonical metadata and maps to TEI biblStruct.

Purpose
-------
Editors pasting a DOI get a deterministic ``<biblStruct>`` populated from
CrossRef's ``/works/{doi}`` endpoint. The mapping intentionally mirrors
the shape produced by the ``tei_bibl_inline`` AI prompt in
``db/seed.py`` so that entries from either source are interchangeable.

Design
------
- Transport: ``httpx.AsyncClient`` per call, no global instance — mirrors
  the other external-service routers (``wikidata``, ``viaf``).
- "Polite pool" identification: CrossRef asks clients to include a
  contact e-mail in the ``User-Agent``; we pull it from the
  ``crossref_contact_email`` setting (falls back to ``admin_email``).
- Pure mapping layer (``crossref_to_biblstruct``) is dependency-free and
  fully unit-testable without the network.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from app.core.exceptions import ExternalServiceError, NotFoundError

logger = structlog.get_logger()

_CROSSREF_API = "https://api.crossref.org/works"
_TIMEOUT = 10.0


# --- Type classification -------------------------------------------------------
#
# CrossRef's ``type`` enum is richer than TEI's ``biblStruct/@type``. We
# collapse the long tail (preprint, posted-content, thesis, report, …) into
# ``other`` to keep the output valid for any TEI schema, and let the editor
# adjust manually if the project uses a specific type vocabulary.

_CROSSREF_TO_TEI: dict[str, str] = {
    "journal-article": "journalArticle",
    "proceedings-article": "journalArticle",
    "book": "book",
    "monograph": "book",
    "reference-book": "book",
    "edited-book": "book",
    "book-chapter": "bookSection",
    "book-section": "bookSection",
    "reference-entry": "bookSection",
}


def _tei_type(crossref_type: str | None) -> str:
    if not crossref_type:
        return "other"
    return _CROSSREF_TO_TEI.get(crossref_type, "other")


# --- Preview + result shapes --------------------------------------------------


@dataclass
class BiblStructPreview:
    """Lightweight structured view shown in the UI before the editor commits."""

    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    container: str | None = None
    publisher: str | None = None
    doi: str | None = None
    type: str | None = None  # TEI-mapped type


@dataclass
class BiblStructResult:
    """Full resolver output — the XML fragment plus the preview."""

    xml_id: str
    biblstruct_xml: str
    preview: BiblStructPreview


# --- DOI shape guard (defensive) ----------------------------------------------


_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)


def looks_like_doi(value: str) -> bool:
    """Return True if *value* matches the minimal DOI shape (10.x/y)."""
    return bool(_DOI_RE.match(value.strip()))


# --- Public API ---------------------------------------------------------------


async def resolve_doi(doi: str, *, contact_email: str = "") -> BiblStructResult:
    """Fetch *doi* from CrossRef and map to TEI biblStruct.

    Raises:
        NotFoundError: CrossRef returned 404 for the DOI.
        ExternalServiceError: any other upstream failure (5xx, timeout,
            parse error). Caller is expected to turn these into 502s.
    """
    doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    if not looks_like_doi(doi):
        raise ExternalServiceError("crossref", f"Malformed DOI: {doi!r}")

    ua = "Aracne2/1.0 (TEI CMS; https://github.com/orazionelson/aracne2)"
    if contact_email:
        ua += f" mailto:{contact_email}"
    headers = {"User-Agent": ua, "Accept": "application/json"}

    url = f"{_CROSSREF_API}/{doi}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(url)
        except httpx.RequestError as exc:
            logger.warning("crossref_request_error", error=str(exc))
            raise ExternalServiceError("crossref", f"Request failed: {exc}") from exc

    if resp.status_code == 404:
        raise NotFoundError(f"DOI {doi!r} not found on CrossRef")
    if resp.status_code != 200:
        raise ExternalServiceError("crossref", f"Upstream HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise ExternalServiceError("crossref", f"Non-JSON response: {exc}") from exc

    message = payload.get("message")
    if not isinstance(message, dict):
        raise ExternalServiceError("crossref", "CrossRef response has no 'message' object")

    return crossref_to_biblstruct(message)


# --- Pure mapping layer --------------------------------------------------------


def _first(seq: Any) -> Any:
    """Return first element of *seq* if it is a non-empty list, else None."""
    if isinstance(seq, list) and seq:
        return seq[0]
    return None


def _extract_year(message: dict[str, Any]) -> int | None:
    """Pick the most reliable year from CrossRef's many date fields.

    Preference order: ``published-print`` > ``published-online`` > ``issued``
    > ``created``. Each carries ``date-parts: [[y, m?, d?]]``.
    """
    for key in ("published-print", "published-online", "issued", "created"):
        entry = message.get(key)
        if not isinstance(entry, dict):
            continue
        parts = _first(entry.get("date-parts"))
        if isinstance(parts, list) and parts:
            try:
                return int(parts[0])
            except (TypeError, ValueError):
                continue
    return None


def _ascii_slug(s: str) -> str:
    """Lowercase ASCII slug used for xml:id generation."""
    normalised = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "", normalised.lower())
    return slug or "anon"


def _xml_id(authors: list[dict[str, Any]], year: int | None, title: str | None) -> str:
    """Generate ``bib_surname_year`` or ``bib_first3titlewords_year``."""
    first_author = _first(authors)
    if isinstance(first_author, dict):
        family = first_author.get("family") or first_author.get("name") or ""
        if isinstance(family, str) and family.strip():
            return f"bib_{_ascii_slug(family)}_{year or 'nd'}"
    if title:
        tokens = re.split(r"\s+", title.strip())[:3]
        return f"bib_{_ascii_slug(' '.join(tokens)) or 'untitled'}_{year or 'nd'}"
    return f"bib_untitled_{year or 'nd'}"


def _person_element(author: dict[str, Any]) -> ET.Element | None:
    """Build ``<author><persName>…</persName></author>`` from a CrossRef author object.

    Returns None when the author has no usable name tokens.
    """
    family = author.get("family")
    given = author.get("given")
    raw_name = author.get("name")

    author_el = ET.Element("author")

    if family or given:
        pers = ET.SubElement(author_el, "persName")
        if family:
            ET.SubElement(pers, "surname").text = str(family).strip()
        if given:
            ET.SubElement(pers, "forename").text = str(given).strip()
    elif raw_name:
        # Organisation-shaped author (rare on CrossRef but possible).
        ET.SubElement(author_el, "orgName").text = str(raw_name).strip()
    else:
        return None

    orcid = author.get("ORCID")
    if isinstance(orcid, str) and orcid:
        # Keep @ref on <persName> so consumers can round-trip to Wikidata
        # matches via the sameAs pathway already used elsewhere in Aracne2.
        if author_el.find("persName") is not None:
            author_el.find("persName").set(  # type: ignore[union-attr]
                "ref", orcid
            )

    return author_el


def _add_imprint(monogr: ET.Element, message: dict[str, Any], year: int | None) -> None:
    """Append ``<imprint>`` with pubPlace / publisher / date when available."""
    imprint = ET.SubElement(monogr, "imprint")
    pub_place = message.get("publisher-location")
    if isinstance(pub_place, str) and pub_place.strip():
        ET.SubElement(imprint, "pubPlace").text = pub_place.strip()
    publisher = message.get("publisher")
    if isinstance(publisher, str) and publisher.strip():
        ET.SubElement(imprint, "publisher").text = publisher.strip()
    if year is not None:
        date_el = ET.SubElement(imprint, "date")
        date_el.set("when", str(year))


def _add_biblscope(monogr: ET.Element, unit: str, value: str | None) -> None:
    if value and value.strip():
        el = ET.SubElement(monogr, "biblScope")
        el.set("unit", unit)
        el.text = value.strip()


def _add_idno(biblstruct: ET.Element, idno_type: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        el = ET.SubElement(biblstruct, "idno")
        el.set("type", idno_type)
        el.text = value.strip()
    elif isinstance(value, list):
        for v in value:
            _add_idno(biblstruct, idno_type, v)


def crossref_to_biblstruct(message: dict[str, Any]) -> BiblStructResult:
    """Map a CrossRef ``message`` object to a TEI ``<biblStruct>`` fragment.

    The output is dependency-light (stdlib ElementTree) and pretty-printed
    with 2-space indentation so a paste into a hand-indented TEI document
    is visually consistent.
    """
    tei_type = _tei_type(message.get("type"))
    authors_raw = message.get("author") or []
    if not isinstance(authors_raw, list):
        authors_raw = []

    title_str = str(_first(message.get("title")) or "").strip() or None
    container_str = str(_first(message.get("container-title")) or "").strip() or None
    year = _extract_year(message)
    doi = (message.get("DOI") or "").strip() or None

    biblstruct = ET.Element("biblStruct")
    xml_id = _xml_id(authors_raw, year, title_str)
    biblstruct.set("xml:id", xml_id)
    biblstruct.set("type", tei_type)

    # Analytic block is present for article- and chapter-shaped references
    # (CrossRef type journalArticle / bookSection). Books carry the author
    # directly inside <monogr>.
    has_analytic = tei_type in {"journalArticle", "bookSection"}
    monogr = ET.Element("monogr")  # temporarily detached; attached after analytic

    if has_analytic:
        analytic = ET.SubElement(biblstruct, "analytic")
        for author in authors_raw:
            if isinstance(author, dict):
                el = _person_element(author)
                if el is not None:
                    analytic.append(el)
        if title_str:
            t = ET.SubElement(analytic, "title")
            t.set("level", "a")
            t.text = title_str
        # Container (journal or host-book) goes into <monogr>.
        if container_str:
            t_m = ET.SubElement(monogr, "title")
            t_m.set("level", "j" if tei_type == "journalArticle" else "m")
            t_m.text = container_str
    else:
        # Books / other — author on the monograph.
        for author in authors_raw:
            if isinstance(author, dict):
                el = _person_element(author)
                if el is not None:
                    monogr.append(el)
        if title_str:
            t = ET.SubElement(monogr, "title")
            t.set("level", "m")
            t.text = title_str

    _add_imprint(monogr, message, year)

    _add_biblscope(monogr, "volume", message.get("volume"))
    _add_biblscope(monogr, "issue", message.get("issue"))
    _add_biblscope(monogr, "page", message.get("page"))

    biblstruct.append(monogr)

    if doi:
        _add_idno(biblstruct, "DOI", doi)
    _add_idno(biblstruct, "ISBN", message.get("ISBN"))
    _add_idno(biblstruct, "ISSN", message.get("ISSN"))

    # Pretty-print in place (ET.indent is stdlib, Python 3.9+).
    ET.indent(biblstruct, space="  ")
    xml = ET.tostring(biblstruct, encoding="unicode")

    preview = BiblStructPreview(
        title=title_str,
        authors=[_author_label(a) for a in authors_raw if isinstance(a, dict) and _author_label(a)],
        year=year,
        container=container_str,
        publisher=message.get("publisher") if isinstance(message.get("publisher"), str) else None,
        doi=doi,
        type=tei_type,
    )

    return BiblStructResult(xml_id=xml_id, biblstruct_xml=xml, preview=preview)


def _author_label(author: dict[str, Any]) -> str:
    """Render an author as a single preview string ("Given Family" or raw name)."""
    family = str(author.get("family") or "").strip()
    given = str(author.get("given") or "").strip()
    if family and given:
        return f"{given} {family}"
    if family:
        return family
    name = str(author.get("name") or "").strip()
    return name
