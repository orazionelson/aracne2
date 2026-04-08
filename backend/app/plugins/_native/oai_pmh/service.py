"""
OAI-PMH Provider — XML response builder.

Implements OAI-PMH 2.0 (http://www.openarchives.org/OAI/openarchivesprotocol.html).

Supported verbs:
  Identify              — repository description
  ListMetadataFormats   — oai_dc only
  ListSets              — one set per published public collection
  ListIdentifiers       — record headers with optional date/set filtering
  ListRecords           — full records (headers + Dublin Core metadata)
  GetRecord             — single record by OAI identifier

Identifier format:  oai:{hostname}:{collection_slug}/{filename}
Datestamp:          collection.updated_at (all documents in a collection share
                    the collection's datestamp — per-document timestamps are not
                    tracked in PostgreSQL)
Pagination:         offset-based resumption tokens (base64-encoded JSON)
Deleted records:    not supported (deletedRecord = "no")
"""

import base64
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import defusedxml.ElementTree as defusedET
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.existdb import ExistDBClient
from app.models.collection import Collection, CollectionStatus

logger = structlog.get_logger()

# ── OAI-PMH namespaces ────────────────────────────────────────────────────────

OAI_NS    = "http://www.openarchives.org/OAI/2.0/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS     = "http://purl.org/dc/elements/1.1/"
XSI_NS    = "http://www.w3.org/2001/XMLSchema-instance"

SUPPORTED_FORMATS: dict[str, dict[str, str]] = {
    "oai_dc": {
        "schema": "http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
        "metadataNamespace": OAI_DC_NS,
    }
}

VALID_VERBS = frozenset(
    {"Identify", "ListMetadataFormats", "ListSets", "ListIdentifiers", "ListRecords", "GetRecord"}
)

PAGE_SIZE = 100

# Register namespace prefixes once at module load.
ET.register_namespace("", OAI_NS)
ET.register_namespace("oai_dc", OAI_DC_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("xsi", XSI_NS)


# ── Date helpers ──────────────────────────────────────────────────────────────

def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


# ── XML helpers ───────────────────────────────────────────────────────────────

def _envelope(base_url: str, verb: str | None = None, **req_attrs: str | None) -> ET.Element:
    """Build the OAI-PMH root element with responseDate and request child."""
    root = ET.Element(
        f"{{{OAI_NS}}}OAI-PMH",
        {
            f"{{{XSI_NS}}}schemaLocation": (
                f"{OAI_NS} {OAI_NS}OAI-PMH.xsd"
            )
        },
    )
    ET.SubElement(root, f"{{{OAI_NS}}}responseDate").text = _fmt(datetime.now(UTC))
    req_el = ET.SubElement(root, f"{{{OAI_NS}}}request")
    if verb:
        req_el.set("verb", verb)
    for k, v in req_attrs.items():
        if v is not None:
            req_el.set(k, v)
    req_el.text = base_url
    return root


def _to_xml(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def _oai_error(
    base_url: str, code: str, message: str, verb: str | None = None
) -> str:
    """Return a complete OAI-PMH error XML response.

    Per spec, badVerb responses must NOT include the verb in <request>.
    """
    root = _envelope(base_url, verb if code != "badVerb" else None)
    ET.SubElement(root, f"{{{OAI_NS}}}error", code=code).text = message
    return _to_xml(root)


# ── Identifier helpers ────────────────────────────────────────────────────────

def _repo_id(base_url: str) -> str:
    return urlparse(base_url).hostname or "aracne2"


def _make_oai_id(repo_id: str, slug: str, filename: str) -> str:
    return f"oai:{repo_id}:{slug}/{filename}"


def _parse_oai_id(identifier: str) -> tuple[str, str] | None:
    """Parse 'oai:{repo}:{slug}/{filename}' → (slug, filename) or None."""
    parts = identifier.split(":", 2)
    if len(parts) != 3 or parts[0] != "oai":
        return None
    try:
        slug, filename = parts[2].split("/", 1)
        return slug, filename
    except ValueError:
        return None


# ── Resumption token ──────────────────────────────────────────────────────────

def _encode_token(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _decode_token(token: str) -> dict[str, Any] | None:
    try:
        return json.loads(base64.urlsafe_b64decode(token.encode()))
    except Exception:
        return None


# ── Database helpers ──────────────────────────────────────────────────────────

async def _published_collections(
    db: AsyncSession,
    set_spec: str | None = None,
    from_dt: datetime | None = None,
    until_dt: datetime | None = None,
) -> list[Collection]:
    stmt = select(Collection).where(
        Collection.status == CollectionStatus.published,
        Collection.is_public.is_(True),
    )
    if set_spec:
        stmt = stmt.where(Collection.slug == set_spec)
    if from_dt:
        stmt = stmt.where(Collection.updated_at >= from_dt)
    if until_dt:
        stmt = stmt.where(Collection.updated_at <= until_dt)
    stmt = stmt.order_by(Collection.published_at)
    return list(await db.scalars(stmt))


async def _collect_docs(
    db: AsyncSession,
    existdb: ExistDBClient,
    set_spec: str | None,
    from_dt: datetime | None,
    until_dt: datetime | None,
) -> list[tuple[Collection, str]]:
    """Return (collection, filename) pairs for all matching published records."""
    cols = await _published_collections(db, set_spec, from_dt, until_dt)
    result: list[tuple[Collection, str]] = []
    for col in cols:
        try:
            filenames = sorted(await existdb.list_collection(col.slug))
        except Exception:
            logger.warning("oai_pmh_list_collection_failed", slug=col.slug)
            filenames = []
        for fn in filenames:
            result.append((col, fn))
    return result


# ── Dublin Core helpers ───────────────────────────────────────────────────────

async def _fetch_tei_dc(
    existdb: ExistDBClient, slug: str, filename: str
) -> dict[str, list[str]]:
    """Extract DC fields from the TEI header via XQuery. Returns {} on failure."""
    try:
        doc_path = f"{existdb.col_path(slug)}/{filename}"
        raw = await existdb.xquery("oai_pmh/get_dc_meta.xq", {"doc_path": doc_path})
        root = defusedET.fromstring(raw)
        out: dict[str, list[str]] = {}
        for child in root:
            text = (child.text or "").strip()
            if text:
                out.setdefault(child.tag, []).append(text)
        return out
    except Exception:
        logger.warning("oai_pmh_tei_dc_failed", slug=slug, filename=filename)
        return {}


def _build_dc_element(
    col: Collection,
    filename: str,
    identifier: str,
    tei: dict[str, list[str]],
) -> ET.Element:
    """Build an <oai_dc:dc> element merging TEI-extracted and collection metadata."""
    dc = ET.Element(
        f"{{{OAI_DC_NS}}}dc",
        {
            f"{{{XSI_NS}}}schemaLocation": (
                f"{OAI_DC_NS} "
                "http://www.openarchives.org/OAI/2.0/oai_dc.xsd"
            )
        },
    )

    def _add(field: str, value: str | None) -> None:
        if value and value.strip():
            ET.SubElement(dc, f"{{{DC_NS}}}{field}").text = value.strip()

    # Title: prefer TEI header, fallback to collection title
    _add("title", (tei.get("title") or [None])[0] or col.title)

    # Creator: prefer TEI authors, fallback to collection author
    creators = tei.get("creator", [])
    if creators:
        for c in creators:
            _add("creator", c)
    elif col.author:
        _add("creator", col.author)

    # Contributors from resp_stmts
    if col.resp_stmts:
        for stmt in col.resp_stmts:
            name = (stmt.get("name") or "").strip()
            resp = (stmt.get("resp") or "").strip()
            if name:
                _add("contributor", f"{name} ({resp})" if resp else name)

    # Publisher: prefer TEI, fallback to collection
    _add("publisher", (tei.get("publisher") or [None])[0] or col.publisher)

    # Date: prefer TEI, fallback to pub_year, then published_at
    date = (tei.get("date") or [None])[0]
    if not date and col.pub_year:
        date = str(col.pub_year)
    if not date and col.published_at:
        date = col.published_at.strftime("%Y-%m-%d")
    _add("date", date)

    # Description: prefer TEI abstract, fallback to collection description
    _add("description", (tei.get("description") or [None])[0] or col.description)

    # Language from TEI header
    _add("language", (tei.get("language") or [None])[0])

    # Fixed DC fields
    ET.SubElement(dc, f"{{{DC_NS}}}type").text = "Text"
    ET.SubElement(dc, f"{{{DC_NS}}}format").text = "application/xml"
    _add("identifier", identifier)

    # Source: place + year if available
    source_parts = [p for p in [col.pub_place, str(col.pub_year) if col.pub_year else None] if p]
    if source_parts:
        _add("source", ", ".join(source_parts))

    return dc


# ── Record element builders ───────────────────────────────────────────────────

def _append_header(
    parent: ET.Element,
    identifier: str,
    datestamp: datetime,
    slug: str,
) -> ET.Element:
    header = ET.SubElement(parent, f"{{{OAI_NS}}}header")
    ET.SubElement(header, f"{{{OAI_NS}}}identifier").text = identifier
    ET.SubElement(header, f"{{{OAI_NS}}}datestamp").text = _fmt(datestamp)
    ET.SubElement(header, f"{{{OAI_NS}}}setSpec").text = slug
    return header


def _append_record(
    parent: ET.Element,
    identifier: str,
    datestamp: datetime,
    slug: str,
    dc: ET.Element,
) -> None:
    record = ET.SubElement(parent, f"{{{OAI_NS}}}record")
    _append_header(record, identifier, datestamp, slug)
    metadata_el = ET.SubElement(record, f"{{{OAI_NS}}}metadata")
    metadata_el.append(dc)


# ── Verb handlers ─────────────────────────────────────────────────────────────

async def _identify(base_url: str, db: AsyncSession) -> str:
    earliest_dt: datetime | None = await db.scalar(
        select(func.min(Collection.published_at)).where(
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
    )
    earliest = _fmt(earliest_dt) if earliest_dt else _fmt(datetime.now(UTC))

    root = _envelope(base_url, "Identify")
    ident = ET.SubElement(root, f"{{{OAI_NS}}}Identify")
    ET.SubElement(ident, f"{{{OAI_NS}}}repositoryName").text = (
        f"{settings.platform_name} OAI-PMH Repository"
    )
    ET.SubElement(ident, f"{{{OAI_NS}}}baseURL").text = base_url
    ET.SubElement(ident, f"{{{OAI_NS}}}protocolVersion").text = "2.0"
    ET.SubElement(ident, f"{{{OAI_NS}}}adminEmail").text = settings.admin_email
    ET.SubElement(ident, f"{{{OAI_NS}}}earliestDatestamp").text = earliest
    ET.SubElement(ident, f"{{{OAI_NS}}}deletedRecord").text = "no"
    ET.SubElement(ident, f"{{{OAI_NS}}}granularity").text = "YYYY-MM-DDThh:mm:ssZ"
    return _to_xml(root)


async def _list_metadata_formats(base_url: str, identifier: str | None) -> str:
    # If identifier is given, verify it exists before listing formats.
    # Since we support oai_dc for all records, we just check identifier syntax.
    if identifier is not None and _parse_oai_id(identifier) is None:
        return _oai_error(
            base_url, "idDoesNotExist",
            f"No record matches identifier: {identifier}",
            "ListMetadataFormats",
        )

    root = _envelope(
        base_url, "ListMetadataFormats",
        identifier=identifier,
    )
    lmf = ET.SubElement(root, f"{{{OAI_NS}}}ListMetadataFormats")
    for prefix, info in SUPPORTED_FORMATS.items():
        mf = ET.SubElement(lmf, f"{{{OAI_NS}}}metadataFormat")
        ET.SubElement(mf, f"{{{OAI_NS}}}metadataPrefix").text = prefix
        ET.SubElement(mf, f"{{{OAI_NS}}}schema").text = info["schema"]
        ET.SubElement(mf, f"{{{OAI_NS}}}metadataNamespace").text = info["metadataNamespace"]
    return _to_xml(root)


async def _list_sets(base_url: str, db: AsyncSession) -> str:
    cols = await _published_collections(db)
    if not cols:
        return _oai_error(base_url, "noSetHierarchy", "No sets available", "ListSets")

    root = _envelope(base_url, "ListSets")
    ls = ET.SubElement(root, f"{{{OAI_NS}}}ListSets")
    for col in cols:
        s = ET.SubElement(ls, f"{{{OAI_NS}}}set")
        ET.SubElement(s, f"{{{OAI_NS}}}setSpec").text = col.slug
        ET.SubElement(s, f"{{{OAI_NS}}}setName").text = col.title
        if col.description:
            sd = ET.SubElement(s, f"{{{OAI_NS}}}setDescription")
            dc = ET.SubElement(sd, f"{{{OAI_DC_NS}}}dc")
            ET.SubElement(dc, f"{{{DC_NS}}}description").text = col.description
    return _to_xml(root)


async def _list_identifiers(
    base_url: str,
    db: AsyncSession,
    existdb: ExistDBClient,
    metadata_prefix: str,
    set_spec: str | None,
    from_dt: datetime | None,
    until_dt: datetime | None,
    offset: int,
) -> str:
    docs = await _collect_docs(db, existdb, set_spec, from_dt, until_dt)
    if not docs:
        return _oai_error(
            base_url, "noRecordsMatch",
            "No records match the specified criteria",
            "ListIdentifiers",
        )

    page = docs[offset: offset + PAGE_SIZE]
    repo_id = _repo_id(base_url)

    root = _envelope(
        base_url, "ListIdentifiers",
        metadataPrefix=metadata_prefix,
        set=set_spec,
        **{"from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if from_dt else None},  # type: ignore[arg-type]
        until=until_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if until_dt else None,
    )
    li = ET.SubElement(root, f"{{{OAI_NS}}}ListIdentifiers")

    for col, filename in page:
        oai_id = _make_oai_id(repo_id, col.slug, filename)
        _append_header(li, oai_id, col.updated_at, col.slug)

    next_offset = offset + PAGE_SIZE
    if next_offset < len(docs):
        token_data: dict[str, Any] = {
            "metadataPrefix": metadata_prefix,
            "offset": next_offset,
        }
        if set_spec:
            token_data["set"] = set_spec
        if from_dt:
            token_data["from"] = _fmt(from_dt)
        if until_dt:
            token_data["until"] = _fmt(until_dt)
        rt = ET.SubElement(li, f"{{{OAI_NS}}}resumptionToken")
        rt.set("completeListSize", str(len(docs)))
        rt.set("cursor", str(offset))
        rt.text = _encode_token(token_data)
    else:
        # Final page: emit empty resumptionToken to signal end of list
        rt = ET.SubElement(li, f"{{{OAI_NS}}}resumptionToken")
        rt.set("completeListSize", str(len(docs)))
        rt.set("cursor", str(offset))

    return _to_xml(root)


async def _list_records(
    base_url: str,
    db: AsyncSession,
    existdb: ExistDBClient,
    metadata_prefix: str,
    set_spec: str | None,
    from_dt: datetime | None,
    until_dt: datetime | None,
    offset: int,
) -> str:
    docs = await _collect_docs(db, existdb, set_spec, from_dt, until_dt)
    if not docs:
        return _oai_error(
            base_url, "noRecordsMatch",
            "No records match the specified criteria",
            "ListRecords",
        )

    page = docs[offset: offset + PAGE_SIZE]
    repo_id = _repo_id(base_url)

    root = _envelope(
        base_url, "ListRecords",
        metadataPrefix=metadata_prefix,
        set=set_spec,
        **{"from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if from_dt else None},  # type: ignore[arg-type]
        until=until_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if until_dt else None,
    )
    lr = ET.SubElement(root, f"{{{OAI_NS}}}ListRecords")

    for col, filename in page:
        oai_id = _make_oai_id(repo_id, col.slug, filename)
        tei = await _fetch_tei_dc(existdb, col.slug, filename)
        dc = _build_dc_element(col, filename, oai_id, tei)
        _append_record(lr, oai_id, col.updated_at, col.slug, dc)

    next_offset = offset + PAGE_SIZE
    if next_offset < len(docs):
        token_data: dict[str, Any] = {
            "metadataPrefix": metadata_prefix,
            "offset": next_offset,
        }
        if set_spec:
            token_data["set"] = set_spec
        if from_dt:
            token_data["from"] = _fmt(from_dt)
        if until_dt:
            token_data["until"] = _fmt(until_dt)
        rt = ET.SubElement(lr, f"{{{OAI_NS}}}resumptionToken")
        rt.set("completeListSize", str(len(docs)))
        rt.set("cursor", str(offset))
        rt.text = _encode_token(token_data)
    else:
        rt = ET.SubElement(lr, f"{{{OAI_NS}}}resumptionToken")
        rt.set("completeListSize", str(len(docs)))
        rt.set("cursor", str(offset))

    return _to_xml(root)


async def _get_record(
    base_url: str,
    db: AsyncSession,
    existdb: ExistDBClient,
    identifier: str,
    metadata_prefix: str,
) -> str:
    parsed = _parse_oai_id(identifier)
    if not parsed:
        return _oai_error(
            base_url, "idDoesNotExist",
            f"No record matches identifier: {identifier}",
            "GetRecord",
        )
    slug, filename = parsed

    # Verify the collection is published and public
    col = await db.scalar(
        select(Collection).where(
            Collection.slug == slug,
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
    )
    if col is None:
        return _oai_error(
            base_url, "idDoesNotExist",
            f"No record matches identifier: {identifier}",
            "GetRecord",
        )

    # Verify the document exists in eXist-db
    try:
        filenames = await existdb.list_collection(slug)
    except Exception:
        filenames = []
    if filename not in filenames:
        return _oai_error(
            base_url, "idDoesNotExist",
            f"No record matches identifier: {identifier}",
            "GetRecord",
        )

    repo_id = _repo_id(base_url)
    oai_id = _make_oai_id(repo_id, slug, filename)
    tei = await _fetch_tei_dc(existdb, slug, filename)
    dc = _build_dc_element(col, filename, oai_id, tei)

    root = _envelope(
        base_url, "GetRecord",
        identifier=identifier,
        metadataPrefix=metadata_prefix,
    )
    gr = ET.SubElement(root, f"{{{OAI_NS}}}GetRecord")
    _append_record(gr, oai_id, col.updated_at, slug, dc)
    return _to_xml(root)


# ── Main dispatcher ───────────────────────────────────────────────────────────

async def dispatch(
    *,
    base_url: str,
    verb: str | None,
    identifier: str | None,
    metadata_prefix: str | None,
    set_spec: str | None,
    from_date: str | None,
    until: str | None,
    resumption_token: str | None,
    db: AsyncSession,
    existdb: ExistDBClient,
) -> str:
    """Route an OAI-PMH request to the appropriate handler."""

    if not verb or verb not in VALID_VERBS:
        return _oai_error(base_url, "badVerb", "Illegal or missing verb argument")

    match verb:
        case "Identify":
            return await _identify(base_url, db)

        case "ListMetadataFormats":
            return await _list_metadata_formats(base_url, identifier)

        case "ListSets":
            return await _list_sets(base_url, db)

        case "ListIdentifiers" | "ListRecords":
            handler = _list_identifiers if verb == "ListIdentifiers" else _list_records

            # resumptionToken is exclusive with selective harvesting params
            if resumption_token is not None:
                token = _decode_token(resumption_token)
                if token is None:
                    return _oai_error(
                        base_url, "badResumptionToken",
                        "The resumptionToken is invalid or expired",
                        verb,
                    )
                return await handler(
                    base_url, db, existdb,
                    metadata_prefix=token.get("metadataPrefix", "oai_dc"),
                    set_spec=token.get("set"),
                    from_dt=_parse_date(token.get("from")),
                    until_dt=_parse_date(token.get("until")),
                    offset=int(token.get("offset", 0)),
                )

            if not metadata_prefix:
                return _oai_error(
                    base_url, "badArgument",
                    "metadataPrefix is required",
                    verb,
                )
            if metadata_prefix not in SUPPORTED_FORMATS:
                return _oai_error(
                    base_url, "cannotDisseminateFormat",
                    f"Metadata format '{metadata_prefix}' is not supported",
                    verb,
                )
            return await handler(
                base_url, db, existdb,
                metadata_prefix=metadata_prefix,
                set_spec=set_spec,
                from_dt=_parse_date(from_date),
                until_dt=_parse_date(until),
                offset=0,
            )

        case "GetRecord":
            if not identifier:
                return _oai_error(base_url, "badArgument", "identifier is required", verb)
            if not metadata_prefix:
                return _oai_error(base_url, "badArgument", "metadataPrefix is required", verb)
            if metadata_prefix not in SUPPORTED_FORMATS:
                return _oai_error(
                    base_url, "cannotDisseminateFormat",
                    f"Metadata format '{metadata_prefix}' is not supported",
                    verb,
                )
            return await _get_record(base_url, db, existdb, identifier, metadata_prefix)

        case _:
            return _oai_error(base_url, "badVerb", "Illegal verb argument")
