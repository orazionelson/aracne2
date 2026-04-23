"""Zotero item → TEI biblStruct mapping + preview projection.

The output shape mirrors what ``app.services.crossref`` produces so that
biblStructs imported from either source are interchangeable in the same
``<listBibl>``. Pure-function module — no DB, no I/O.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from app.plugins.zotero_import.schemas import ZoteroItemPreview


# Zotero itemType → TEI biblStruct/@type. Long tail collapses to "other"
# (same convention used by the CrossRef resolver). Types that are not
# bibliographic at all (note/attachment/annotation) are filtered out in
# the client layer before they reach the mapper.
_ITEM_TYPE_MAP: dict[str, str] = {
    "journalArticle": "journalArticle",
    "magazineArticle": "journalArticle",
    "newspaperArticle": "journalArticle",
    "conferencePaper": "journalArticle",
    "book": "book",
    "manuscript": "book",
    "report": "book",
    "thesis": "book",
    "encyclopediaArticle": "bookSection",
    "dictionaryEntry": "bookSection",
    "bookSection": "bookSection",
    # Zotero uses "bookChapter" in some exports; be lenient.
    "bookChapter": "bookSection",
}


def _tei_type(zotero_type: str | None) -> str:
    if not zotero_type:
        return "other"
    return _ITEM_TYPE_MAP.get(zotero_type, "other")


_YEAR_RE = re.compile(r"\b(1\d{3}|20\d{2}|21\d{2})\b")


def _extract_year(raw_date: str | None) -> int | None:
    """Zotero's ``date`` is a free-text field (``"March 1998"``, ``"c.1500"``,
    ``"1998-06-15"``); we just pull the first 4-digit year-looking token."""
    if not raw_date:
        return None
    match = _YEAR_RE.search(raw_date)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _author_like_creators(creators: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Keep only creators with ``creatorType`` in {author, editor,
    contributor}. Zotero also stores translators, seriesEditors, etc. —
    the biblStruct shape we target cares mainly about authors and
    editors; translators appear as author-equivalent in practice."""
    if not isinstance(creators, list):
        return []
    accepted = {"author", "editor", "contributor", "translator"}
    return [
        c for c in creators
        if isinstance(c, dict) and c.get("creatorType") in accepted
    ]


def _first_author_family(creators: list[dict[str, Any]]) -> str | None:
    for c in creators:
        family = c.get("lastName")
        name = c.get("name")
        if isinstance(family, str) and family.strip():
            return family.strip()
        # "name" is Zotero's one-field form for organisations / single-name creators
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _ascii_slug(s: str) -> str:
    import unicodedata
    normalised = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "", normalised.lower())
    return slug or "anon"


def _xml_id(creators: list[dict[str, Any]], year: int | None, title: str | None) -> str:
    family = _first_author_family(creators)
    if family:
        return f"bib_{_ascii_slug(family)}_{year or 'nd'}"
    if title:
        tokens = re.split(r"\s+", title.strip())[:3]
        return f"bib_{_ascii_slug(' '.join(tokens)) or 'untitled'}_{year or 'nd'}"
    return f"bib_untitled_{year or 'nd'}"


def _person_or_org_element(creator: dict[str, Any]) -> ET.Element | None:
    """Build an ``<author>`` / ``<editor>`` element from a Zotero creator."""
    role = creator.get("creatorType") or "author"
    # TEI uses <editor> for editorial credit; translator/contributor fold
    # into <author> with @role for MVP simplicity.
    tag = "editor" if role == "editor" else "author"
    el = ET.Element(tag)
    if role in {"translator", "contributor"}:
        el.set("role", role)

    first = creator.get("firstName")
    last = creator.get("lastName")
    one_field = creator.get("name")

    if last or first:
        pers = ET.SubElement(el, "persName")
        if last:
            ET.SubElement(pers, "surname").text = str(last).strip()
        if first:
            ET.SubElement(pers, "forename").text = str(first).strip()
    elif one_field:
        # Zotero's ``name`` mode — org or single-token author. Use
        # <orgName> when it looks institutional, else <persName><surname>.
        ET.SubElement(el, "orgName").text = str(one_field).strip()
    else:
        return None
    return el


def _add_imprint(monogr: ET.Element, data: dict[str, Any], year: int | None) -> None:
    imprint = ET.SubElement(monogr, "imprint")
    place = data.get("place")
    if isinstance(place, str) and place.strip():
        ET.SubElement(imprint, "pubPlace").text = place.strip()
    publisher = data.get("publisher")
    if isinstance(publisher, str) and publisher.strip():
        ET.SubElement(imprint, "publisher").text = publisher.strip()
    if year is not None:
        d = ET.SubElement(imprint, "date")
        d.set("when", str(year))


def _add_biblscope(monogr: ET.Element, unit: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        el = ET.SubElement(monogr, "biblScope")
        el.set("unit", unit)
        el.text = value.strip()


def _add_idno(biblstruct: ET.Element, type_: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        el = ET.SubElement(biblstruct, "idno")
        el.set("type", type_)
        el.text = value.strip()


def zotero_item_to_biblstruct(data: dict[str, Any]) -> str:
    """Map a Zotero ``data`` object to a ``<biblStruct>`` XML fragment.

    The returned string is pretty-printed with 2-space indentation so it
    fits cleanly inside a ``<listBibl>`` block.
    """
    item_type = data.get("itemType")
    tei_type = _tei_type(item_type)
    creators = _author_like_creators(data.get("creators"))
    title = str(data.get("title") or "").strip() or None
    publication_title = str(data.get("publicationTitle") or "").strip() or None
    book_title = str(data.get("bookTitle") or "").strip() or None
    container = publication_title or book_title
    year = _extract_year(data.get("date") if isinstance(data.get("date"), str) else None)
    doi = str(data.get("DOI") or "").strip() or None
    isbn = str(data.get("ISBN") or "").strip() or None
    issn = str(data.get("ISSN") or "").strip() or None

    biblstruct = ET.Element("biblStruct")
    biblstruct.set("xml:id", _xml_id(creators, year, title))
    biblstruct.set("type", tei_type)

    has_analytic = tei_type in {"journalArticle", "bookSection"}
    monogr = ET.Element("monogr")

    if has_analytic:
        analytic = ET.SubElement(biblstruct, "analytic")
        for c in creators:
            if c.get("creatorType") != "editor":
                el = _person_or_org_element(c)
                if el is not None:
                    analytic.append(el)
        if title:
            t = ET.SubElement(analytic, "title")
            t.set("level", "a")
            t.text = title
        if container:
            tm = ET.SubElement(monogr, "title")
            tm.set("level", "j" if tei_type == "journalArticle" else "m")
            tm.text = container
        # Editors and translators of the host work live on <monogr>.
        for c in creators:
            if c.get("creatorType") in {"editor", "translator"}:
                el = _person_or_org_element(c)
                if el is not None:
                    monogr.append(el)
    else:
        for c in creators:
            el = _person_or_org_element(c)
            if el is not None:
                monogr.append(el)
        if title:
            t = ET.SubElement(monogr, "title")
            t.set("level", "m")
            t.text = title

    _add_imprint(monogr, data, year)
    _add_biblscope(monogr, "volume", data.get("volume"))
    _add_biblscope(monogr, "issue", data.get("issue"))
    _add_biblscope(monogr, "page", data.get("pages"))

    biblstruct.append(monogr)

    _add_idno(biblstruct, "DOI", doi)
    _add_idno(biblstruct, "ISBN", isbn)
    _add_idno(biblstruct, "ISSN", issn)
    url = data.get("url")
    _add_idno(biblstruct, "URL", url)

    ET.indent(biblstruct, space="  ")
    return ET.tostring(biblstruct, encoding="unicode")


def zotero_item_to_preview(key: str, data: dict[str, Any]) -> ZoteroItemPreview:
    """Compact projection used in the preview modal."""
    creators = _author_like_creators(data.get("creators"))
    author_labels: list[str] = []
    for c in creators:
        first = str(c.get("firstName") or "").strip()
        last = str(c.get("lastName") or "").strip()
        name = str(c.get("name") or "").strip()
        if last and first:
            author_labels.append(f"{first} {last}")
        elif last:
            author_labels.append(last)
        elif name:
            author_labels.append(name)
    title = str(data.get("title") or "").strip() or "(untitled)"
    year = _extract_year(data.get("date") if isinstance(data.get("date"), str) else None)
    doi = str(data.get("DOI") or "").strip() or None
    return ZoteroItemPreview(
        key=key,
        item_type=str(data.get("itemType") or "unknown"),
        title=title,
        creators=author_labels,
        year=year,
        doi=doi,
    )
