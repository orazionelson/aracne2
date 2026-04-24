"""OpenAlex search client and biblStruct mapper.

Upstream::

    GET https://api.openalex.org/works?search={q}&per-page={rows}
        [&mailto={contact_email}]

Response (abridged)::

    {
      "results": [
        {
          "id": "https://openalex.org/W2741809807",
          "doi": "https://doi.org/10.7717/peerj.4375",
          "title": "Tuning the activity of ...",
          "publication_year": 2018,
          "type": "article",
          "authorships": [
            {"author": {"display_name": "Jane Doe"}, "raw_author_name": "Doe, J."}
          ],
          "primary_location": {"source": {"display_name": "PeerJ",
                                          "host_organization_name": "PeerJ Inc."}},
          ...
        }
      ],
      "meta": {...}
    }

No authentication required. OpenAlex separates requests into a
"polite pool" (with ``?mailto=…``) and a "common pool" (without),
granting higher priority to polite callers. The plugin pulls the
mailto from ``openalex_contact_email`` in ``system_settings`` and
falls back to ``admin_email``.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Any

import httpx
import structlog

from app.plugins.openalex.schemas import OpenAlexHit, OpenAlexPreview

logger = structlog.get_logger()

_SEARCH_URL = "https://api.openalex.org/works"
_TIMEOUT = 10.0

# OpenAlex → TEI type collapsing (same tiers as CrossRef plugin).
_OPENALEX_TO_TEI: dict[str, str] = {
    "article": "journalArticle",
    "journal-article": "journalArticle",
    "proceedings-article": "journalArticle",
    "book": "book",
    "monograph": "book",
    "reference-book": "book",
    "edited-book": "book",
    "book-chapter": "bookSection",
    "book-section": "bookSection",
    "dissertation": "book",
    "preprint": "journalArticle",
    "posted-content": "journalArticle",
}


async def search(
    q: str,
    *,
    rows: int = 10,
    contact_email: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[OpenAlexHit]:
    """Return up to ``rows`` works matching ``q``, each with a
    ready-to-insert biblStruct XML fragment.

    Fail-soft: any upstream problem surfaces as an empty list.
    """
    rows = max(1, min(rows, 25))
    params = {"search": q, "per-page": str(rows)}
    if contact_email.strip():
        params["mailto"] = contact_email.strip()

    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-OpenAlex/1.0",
    }

    kwargs: dict[str, Any] = {
        "timeout": _TIMEOUT,
        "follow_redirects": True,
        "headers": headers,
    }
    if transport is not None:
        kwargs["transport"] = transport

    try:
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(_SEARCH_URL, params=params)
    except httpx.RequestError as exc:
        logger.warning("openalex_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("openalex_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("openalex_search_parse_error", error=str(exc))
        return []

    results = payload.get("results") or []
    if not isinstance(results, list):
        return []

    hits: list[OpenAlexHit] = []
    for row in results[:rows]:
        if not isinstance(row, dict):
            continue
        hit = _row_to_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


# ── Pure mapping ─────────────────────────────────────────────────────────────


def _row_to_hit(row: dict[str, Any]) -> OpenAlexHit | None:
    raw_id = row.get("id")
    if not isinstance(raw_id, str) or "openalex.org/" not in raw_id:
        return None
    openalex_id = raw_id.rsplit("/", 1)[-1]
    if not openalex_id.startswith("W"):
        return None

    title = row.get("title") or row.get("display_name")
    if not isinstance(title, str) or not title.strip():
        return None

    doi = _extract_doi(row.get("doi"))
    year = _as_int(row.get("publication_year"))
    tei_type = _OPENALEX_TO_TEI.get(str(row.get("type") or "").lower(), "other")
    authors = _extract_authors(row.get("authorships") or [])
    container, publisher = _extract_venue(row)

    preview = OpenAlexPreview(
        title=title.strip(),
        authors=[a["display"] for a in authors if a.get("display")],
        year=year,
        type=tei_type,
        container=container,
        publisher=publisher,
        doi=doi,
        openalex_id=openalex_id,
        uri=raw_id,
    )

    xml_id = _xml_id(authors, year, title)
    biblstruct_xml = _build_biblstruct(preview, authors, xml_id)

    return OpenAlexHit(
        xml_id=xml_id,
        biblstruct_xml=biblstruct_xml,
        preview=preview,
    )


def _extract_doi(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    doi = raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi or None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_authors(authorships: list[Any]) -> list[dict[str, str]]:
    """Pull a list of ``{family, given, display, orcid}`` dicts."""
    out: list[dict[str, str]] = []
    for au in authorships:
        if not isinstance(au, dict):
            continue
        author = au.get("author") or {}
        if not isinstance(author, dict):
            continue
        display = (
            author.get("display_name")
            or au.get("raw_author_name")
            or ""
        )
        if not isinstance(display, str) or not display.strip():
            continue
        # OpenAlex does not split display_name into family/given. We try
        # a best-effort split on the last comma ("Doe, Jane") or the
        # last space ("Jane Doe") — good enough for the 80% case.
        display = display.strip()
        family, given = _split_name(display)
        orcid = author.get("orcid")
        out.append({
            "family": family,
            "given": given,
            "display": display,
            "orcid": orcid if isinstance(orcid, str) else "",
        })
    return out


def _split_name(display: str) -> tuple[str, str]:
    if "," in display:
        family, _, given = display.partition(",")
        return family.strip(), given.strip()
    # "Jane Doe" → given "Jane", family "Doe".
    parts = display.rsplit(" ", 1)
    if len(parts) == 2:
        return parts[1].strip(), parts[0].strip()
    return display.strip(), ""


def _extract_venue(row: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (container_title, publisher) best-effort."""
    # New shape: row["primary_location"]["source"]["display_name"].
    for key in ("primary_location", "best_oa_location", "host_venue"):
        entry = row.get(key)
        if isinstance(entry, dict):
            source = entry.get("source") if key != "host_venue" else entry
            if isinstance(source, dict):
                name = source.get("display_name")
                pub = (
                    source.get("host_organization_name")
                    or source.get("publisher")
                )
                return (
                    name.strip() if isinstance(name, str) and name.strip() else None,
                    pub.strip() if isinstance(pub, str) and pub.strip() else None,
                )
    return None, None


# ── xml:id + biblStruct XML builders ─────────────────────────────────────────


def _ascii_slug(s: str) -> str:
    normalised = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "", normalised.lower())
    return slug or "anon"


def _xml_id(authors: list[dict[str, str]], year: int | None, title: str | None) -> str:
    if authors and authors[0].get("family"):
        return f"bib_{_ascii_slug(authors[0]['family'])}_{year or 'nd'}"
    if title:
        tokens = re.split(r"\s+", title.strip())[:3]
        return f"bib_{_ascii_slug(' '.join(tokens)) or 'untitled'}_{year or 'nd'}"
    return f"bib_untitled_{year or 'nd'}"


def _build_biblstruct(
    preview: OpenAlexPreview,
    authors: list[dict[str, str]],
    xml_id: str,
) -> str:
    """Emit a ``<biblStruct>`` whose shape mirrors the CrossRef plugin."""
    root = ET.Element("biblStruct", {"xml:id": xml_id, "type": preview.type or "other"})

    if preview.type == "journalArticle":
        analytic = ET.SubElement(root, "analytic")
        ET.SubElement(analytic, "title", {"level": "a"}).text = preview.title
        for a in authors:
            _append_author(analytic, a)
        if preview.doi:
            ET.SubElement(analytic, "idno", {"type": "DOI"}).text = preview.doi
        ET.SubElement(analytic, "idno", {"type": "OpenAlex"}).text = preview.openalex_id
        monogr = ET.SubElement(root, "monogr")
        if preview.container:
            ET.SubElement(monogr, "title", {"level": "j"}).text = preview.container
        imprint = ET.SubElement(monogr, "imprint")
        if preview.publisher:
            ET.SubElement(imprint, "publisher").text = preview.publisher
        if preview.year:
            ET.SubElement(imprint, "date", {"when": str(preview.year)}).text = str(preview.year)
    elif preview.type in ("book", "bookSection"):
        if preview.type == "bookSection":
            analytic = ET.SubElement(root, "analytic")
            ET.SubElement(analytic, "title", {"level": "a"}).text = preview.title
            for a in authors:
                _append_author(analytic, a)
            monogr = ET.SubElement(root, "monogr")
            if preview.container:
                ET.SubElement(monogr, "title", {"level": "m"}).text = preview.container
        else:
            monogr = ET.SubElement(root, "monogr")
            ET.SubElement(monogr, "title", {"level": "m"}).text = preview.title
            for a in authors:
                _append_author(monogr, a)
        imprint = ET.SubElement(monogr, "imprint")
        if preview.publisher:
            ET.SubElement(imprint, "publisher").text = preview.publisher
        if preview.year:
            ET.SubElement(imprint, "date", {"when": str(preview.year)}).text = str(preview.year)
        if preview.doi:
            ET.SubElement(monogr, "idno", {"type": "DOI"}).text = preview.doi
        ET.SubElement(monogr, "idno", {"type": "OpenAlex"}).text = preview.openalex_id
    else:
        monogr = ET.SubElement(root, "monogr")
        ET.SubElement(monogr, "title").text = preview.title
        for a in authors:
            _append_author(monogr, a)
        imprint = ET.SubElement(monogr, "imprint")
        if preview.publisher:
            ET.SubElement(imprint, "publisher").text = preview.publisher
        if preview.year:
            ET.SubElement(imprint, "date", {"when": str(preview.year)}).text = str(preview.year)
        if preview.doi:
            ET.SubElement(monogr, "idno", {"type": "DOI"}).text = preview.doi
        ET.SubElement(monogr, "idno", {"type": "OpenAlex"}).text = preview.openalex_id

    return ET.tostring(root, encoding="unicode")


def _append_author(parent: ET.Element, author: dict[str, str]) -> None:
    au = ET.SubElement(parent, "author")
    family = author.get("family") or ""
    given = author.get("given") or ""
    if family or given:
        pers = ET.SubElement(au, "persName")
        if family:
            ET.SubElement(pers, "surname").text = family
        if given:
            ET.SubElement(pers, "forename").text = given
        orcid = author.get("orcid")
        if orcid:
            pers.set("ref", orcid)
    else:
        ET.SubElement(au, "orgName").text = author.get("display") or ""
