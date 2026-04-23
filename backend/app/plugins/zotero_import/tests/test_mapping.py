"""Unit tests for the Zotero → TEI mapping layer (pure, no DB, no net)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import pytest

from app.plugins.zotero_import.mapping import (
    zotero_item_to_biblstruct,
    zotero_item_to_preview,
)


# ── preview projection ─────────────────────────────────────────────────────


def test_preview_joins_first_and_last_names() -> None:
    prev = zotero_item_to_preview(
        "ABC1234",
        {
            "itemType": "journalArticle",
            "title": "On Something",
            "creators": [
                {"creatorType": "author", "firstName": "John", "lastName": "Smith"},
                {"creatorType": "author", "lastName": "Doe"},
            ],
            "date": "1998",
            "DOI": "10.1234/xyz",
        },
    )
    assert prev.key == "ABC1234"
    assert prev.title == "On Something"
    assert prev.creators == ["John Smith", "Doe"]
    assert prev.year == 1998
    assert prev.doi == "10.1234/xyz"


def test_preview_extracts_year_from_free_text_date() -> None:
    prev = zotero_item_to_preview(
        "K", {"itemType": "book", "title": "x", "date": "March 1998"}
    )
    assert prev.year == 1998


def test_preview_tolerates_name_only_creator() -> None:
    prev = zotero_item_to_preview(
        "K",
        {
            "itemType": "book",
            "title": "x",
            "creators": [{"creatorType": "author", "name": "Aristotle"}],
        },
    )
    assert prev.creators == ["Aristotle"]


def test_preview_filters_non_bibliographic_creator_types() -> None:
    prev = zotero_item_to_preview(
        "K",
        {
            "itemType": "book",
            "title": "x",
            "creators": [
                {"creatorType": "author", "firstName": "A", "lastName": "B"},
                {"creatorType": "seriesEditor", "firstName": "Skip", "lastName": "Me"},
            ],
        },
    )
    # seriesEditor is not in {author, editor, contributor, translator}.
    assert prev.creators == ["A B"]


# ── biblStruct shape ───────────────────────────────────────────────────────


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def test_mapping_journal_article_shape() -> None:
    data: dict[str, Any] = {
        "itemType": "journalArticle",
        "title": "On Something",
        "creators": [
            {"creatorType": "author", "firstName": "John", "lastName": "Smith"},
        ],
        "publicationTitle": "Journal of Y",
        "publisher": "Springer",
        "place": "Berlin",
        "volume": "12",
        "issue": "3",
        "pages": "45-67",
        "date": "1998-06-15",
        "DOI": "10.1234/xyz",
    }
    xml = zotero_item_to_biblstruct(data)
    root = _parse(xml)
    assert root.get("type") == "journalArticle"

    analytic = root.find("analytic")
    assert analytic is not None
    a_title = analytic.find("title")
    assert a_title is not None and a_title.get("level") == "a"
    assert a_title.text == "On Something"
    # Author sits in analytic for articles.
    assert analytic.find("author/persName/surname").text == "Smith"  # type: ignore[union-attr]

    monogr = root.find("monogr")
    assert monogr is not None
    j_title = monogr.find("title")
    assert j_title is not None and j_title.get("level") == "j"
    assert j_title.text == "Journal of Y"

    imprint = monogr.find("imprint")
    assert imprint is not None
    assert imprint.find("pubPlace").text == "Berlin"  # type: ignore[union-attr]
    assert imprint.find("publisher").text == "Springer"  # type: ignore[union-attr]
    assert imprint.find("date").get("when") == "1998"  # type: ignore[union-attr]

    scopes = {s.get("unit"): s.text for s in monogr.findall("biblScope")}
    assert scopes == {"volume": "12", "issue": "3", "page": "45-67"}

    idnos = {idno.get("type"): idno.text for idno in root.findall("idno")}
    assert idnos["DOI"] == "10.1234/xyz"


def test_mapping_book_places_author_on_monogr() -> None:
    data: dict[str, Any] = {
        "itemType": "book",
        "title": "Book Title",
        "creators": [
            {"creatorType": "author", "firstName": "J.", "lastName": "Smith"},
        ],
        "publisher": "Routledge",
        "place": "London",
        "date": "2000",
        "ISBN": "978-0-00-000000-0",
    }
    xml = zotero_item_to_biblstruct(data)
    root = _parse(xml)
    assert root.get("type") == "book"
    assert root.find("analytic") is None
    monogr = root.find("monogr")
    assert monogr is not None
    assert monogr.find("author/persName/surname").text == "Smith"  # type: ignore[union-attr]
    assert monogr.find("title").get("level") == "m"  # type: ignore[union-attr]
    idnos = {idno.get("type"): idno.text for idno in root.findall("idno")}
    assert idnos.get("ISBN") == "978-0-00-000000-0"


def test_mapping_book_section_has_analytic_plus_host() -> None:
    data: dict[str, Any] = {
        "itemType": "bookSection",
        "title": "Chapter Title",
        "creators": [
            {"creatorType": "author", "firstName": "A.", "lastName": "Author"},
            {"creatorType": "editor", "firstName": "E.", "lastName": "Editor"},
        ],
        "bookTitle": "Host Book",
        "publisher": "Cambridge UP",
        "date": "2005",
        "pages": "100-120",
    }
    xml = zotero_item_to_biblstruct(data)
    root = _parse(xml)
    assert root.get("type") == "bookSection"
    analytic = root.find("analytic")
    assert analytic is not None
    assert analytic.find("title").get("level") == "a"  # type: ignore[union-attr]
    # The editor belongs to the host monograph, not the analytic.
    monogr = root.find("monogr")
    assert monogr is not None
    assert monogr.find("title").get("level") == "m"  # type: ignore[union-attr]
    assert monogr.find("title").text == "Host Book"  # type: ignore[union-attr]
    assert monogr.find("editor/persName/surname").text == "Editor"  # type: ignore[union-attr]


def test_mapping_unknown_type_collapses_to_other() -> None:
    xml = zotero_item_to_biblstruct(
        {"itemType": "audioRecording", "title": "Something", "date": "2024"}
    )
    root = _parse(xml)
    assert root.get("type") == "other"
    assert root.find("analytic") is None


def test_mapping_xml_id_uses_first_author_surname_and_year() -> None:
    xml = zotero_item_to_biblstruct(
        {
            "itemType": "book",
            "title": "x",
            "creators": [
                {"creatorType": "author", "firstName": "Dante", "lastName": "Alighieri"},
            ],
            "date": "1321",
        }
    )
    assert 'xml:id="bib_alighieri_1321"' in xml


def test_mapping_xml_id_falls_back_to_title_words() -> None:
    xml = zotero_item_to_biblstruct(
        {"itemType": "book", "title": "Grammar of Old Occitan", "date": "1975"}
    )
    # First three words joined + year.
    assert 'xml:id="bib_grammarofold_1975"' in xml
