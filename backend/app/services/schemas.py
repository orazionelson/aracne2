"""
schemas — TEI schema management service.

Handles file storage, URL import (with SSRF guard), XML validation against
RNG / DTD / XSD schemas using lxml, and CM5 schema generation.

Security — SSRF guard on URL import
-------------------------------------
When a user supplies a URL to import a schema, this service resolves the
hostname to an IP address and blocks any address that is private, loopback,
link-local, multicast or otherwise reserved.

Design choice: we block private IP ranges rather than maintaining a domain
allowlist.  TEI schemas are published by many institutions worldwide
(tei-c.org, universities, research projects) and a whitelist would be far
too restrictive.  Blocking private IPs prevents the most common SSRF attack
vectors — internal metadata APIs, databases, and other containers on the
same Docker network — while allowing any legitimate public schema source.

Note: the DNS lookup (``socket.gethostbyname``) runs synchronously.  It is
a one-time, admin-only action that completes in under 100 ms in the common
case; running it in a thread executor is intentionally deferred for now.

CM5 schema generation
---------------------
``generate_cm5`` extracts an element-to-children / element-to-attrs mapping
from the already-uploaded validation schema (RNG, XSD, or DTD) and writes
the ``<cm_tei_schema>`` XML consumed by CodeMirror 5's xml-hint addon.

Algorithm overview:
- **RNG**: recursively resolves ``<ref>`` elements against the define map,
  stopping at ``<element>`` boundaries to collect child element names;
  stops at ``<element>`` boundaries again when collecting attributes.
  Cycles are prevented by a frozenset of visited define names.
- **XSD**: follows ``<xs:group ref>`` chains to collect child element refs;
  follows ``<xs:attributeGroup ref>`` chains to collect attributes.
- **DTD**: uses lxml's built-in DTD parser which exposes the parsed content
  model tree directly (``ElementContent`` left/right nodes).
"""

import ipaddress
import socket
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import DomainValidationError, ExternalServiceError, NotFoundError
from app.models.tei_schema import SchemaFormat, TeiSchema
from app.models.user import User
from app.schemas.tei_schemas import TeiSchemaCreate, TeiSchemaResponse, ValidationError, ValidationResult

logger = structlog.get_logger()

# Maximum size (bytes) accepted when importing a schema via URL
_MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB

# Parser for user-supplied XML documents: external entities and network disabled (XXE prevention).
_safe_xml_parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
)

# Parser for schema files we stored ourselves (RNG/XSD).
# Entity resolution is disabled; network is enabled so that xs:import
# directives can attempt to fetch external schemas.
_schema_xml_parser = etree.XMLParser(
    resolve_entities=False,
    no_network=False,
    load_dtd=True,
)

_XSD_NS = "http://www.w3.org/2001/XMLSchema"
_RNG_NS = "http://relaxng.org/ns/structure/1.0"
_XML_NS = "http://www.w3.org/XML/1998/namespace"


def _build_xmlschema(schema_path: Path) -> etree.XMLSchema:
    """Load an XSD schema, stripping unresolvable xs:import directives.

    Some TEI XSD schemas (notably tei_all.xsd) import external namespaces
    such as ISOcat DCR (http://www.isocat.org/ns/dcr) that are no longer
    available on the internet. lxml's XMLSchema compiler raises
    XMLSchemaParseError when it cannot resolve an xs:import target.

    Strategy: if XMLSchema compilation fails, remove the xs:import element
    whose namespace matches the error and retry. Repeat until the schema
    compiles or no more imports can be removed. This is safe because:
    - The removed namespaces are external attribute decorators (DCR tags),
      not structural TEI elements — stripping them does not change how TEI
      content is validated.
    - The schema file itself is trusted (uploaded/imported by an admin).
    """
    tree = etree.parse(str(schema_path), parser=_schema_xml_parser)
    root = tree.getroot()

    for _ in range(20):  # safety cap — a schema won't have more than 20 bad imports
        try:
            return etree.XMLSchema(tree)
        except etree.XMLSchemaParseError as exc:
            msg = str(exc)
            # Extract the offending namespace from the error message.
            # Typical format: "… '{http://some.ns/}attr' does not resolve …"
            import re as _re
            match = _re.search(r"'\{([^}]+)\}", msg)
            if not match:
                raise  # unknown error shape — propagate as-is

            bad_ns = match.group(1)
            # Find and remove all xs:import elements for that namespace.
            imports = root.findall(f"{{{_XSD_NS}}}import[@namespace='{bad_ns}']")
            if not imports:
                raise  # can't fix it — propagate
            for imp in imports:
                root.remove(imp)
                logger.debug("xsd_import_stripped", namespace=bad_ns)

    # Should never reach here given the cap above.
    return etree.XMLSchema(tree)

_FORMAT_EXT: dict[SchemaFormat, str] = {
    SchemaFormat.rng: "rng",
    SchemaFormat.dtd: "dtd",
    SchemaFormat.xsd: "xsd",
}


# ── File paths ─────────────────────────────────────────────────────────────────

def _schema_dir(schema_id: uuid.UUID) -> Path:
    return settings.schemas_dir / str(schema_id)


def _validation_path(schema_id: uuid.UUID, fmt: SchemaFormat) -> Path:
    return _schema_dir(schema_id) / f"validation.{_FORMAT_EXT[fmt]}"


def _cm5_path(schema_id: uuid.UUID) -> Path:
    return _schema_dir(schema_id) / "cm5.xml"


def _ensure_schema_dir(schema_id: uuid.UUID) -> Path:
    d = _schema_dir(schema_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── SSRF guard ─────────────────────────────────────────────────────────────────

def _check_ssrf(url: str) -> None:
    """Raise DomainValidationError if the URL resolves to a non-public address.

    See module docstring for the rationale behind this design choice.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DomainValidationError("INVALID_URL", "Only http:// and https:// URLs are allowed.")
    hostname = parsed.hostname or ""
    if not hostname:
        raise DomainValidationError("INVALID_URL", "URL must include a hostname.")
    try:
        ip_str = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(ip_str)
    except (socket.gaierror, ValueError) as exc:
        raise DomainValidationError(
            "INVALID_URL", f"Cannot resolve hostname {hostname!r}: {exc}"
        ) from exc
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
    ):
        raise DomainValidationError(
            "SSRF_BLOCKED",
            f"URL resolves to a non-public address ({addr}). "
            "Importing schemas from private or internal hosts is not permitted.",
        )


# ── Validation helpers ─────────────────────────────────────────────────────────

def _errors_from_log(log: etree._ListErrorLog) -> list[ValidationError]:  # type: ignore[name-defined]
    return [
        ValidationError(line=e.line, col=e.column, message=e.message)
        for e in log
    ]


def _validate_rng(xml_bytes: bytes, schema_path: Path) -> list[ValidationError]:
    try:
        schema_doc = etree.parse(str(schema_path), parser=_schema_xml_parser)
        relaxng = etree.RelaxNG(schema_doc)
    except etree.LxmlError as exc:
        raise DomainValidationError(
            "SCHEMA_PARSE_ERROR",
            f"The RNG schema file could not be loaded: {exc}",
        ) from exc
    try:
        doc = etree.fromstring(xml_bytes, parser=_safe_xml_parser)
    except etree.XMLSyntaxError as exc:
        return [ValidationError(line=exc.lineno or 0, col=exc.offset or 0, message=str(exc))]
    relaxng.validate(doc)
    return _errors_from_log(relaxng.error_log)


def _validate_dtd(xml_bytes: bytes, schema_path: Path) -> list[ValidationError]:
    try:
        dtd = etree.DTD(file=str(schema_path))
    except etree.LxmlError as exc:
        raise DomainValidationError(
            "SCHEMA_PARSE_ERROR",
            f"The DTD schema file could not be loaded: {exc}",
        ) from exc
    try:
        doc = etree.fromstring(xml_bytes, parser=_safe_xml_parser)
    except etree.XMLSyntaxError as exc:
        return [ValidationError(line=exc.lineno or 0, col=exc.offset or 0, message=str(exc))]
    dtd.validate(doc)
    return _errors_from_log(dtd.error_log)


def _validate_xsd(xml_bytes: bytes, schema_path: Path) -> list[ValidationError]:
    try:
        xmlschema = _build_xmlschema(schema_path)
    except etree.LxmlError as exc:
        raise DomainValidationError(
            "SCHEMA_PARSE_ERROR",
            f"The XSD schema file could not be loaded: {exc}",
        ) from exc
    try:
        doc = etree.fromstring(xml_bytes, parser=_safe_xml_parser)
    except etree.XMLSyntaxError as exc:
        return [ValidationError(line=exc.lineno or 0, col=exc.offset or 0, message=str(exc))]
    xmlschema.validate(doc)
    return _errors_from_log(xmlschema.error_log)


def validate_xml(xml_bytes: bytes, schema: TeiSchema) -> ValidationResult:
    """Validate *xml_bytes* against the validation schema attached to *schema*.

    Returns a ValidationResult with ``valid=True`` and an empty error list
    when the document is valid.  If the schema has no validation file,
    raises DomainValidationError.
    """
    if not schema.validation_filename or not schema.validation_format:
        raise DomainValidationError(
            "NO_VALIDATION_FILE", "This schema has no validation file attached."
        )
    path = _validation_path(schema.id, schema.validation_format)
    if not path.exists():
        raise DomainValidationError(
            "MISSING_SCHEMA_FILE",
            "Validation schema file is missing on the server — please re-upload it.",
        )

    fmt = schema.validation_format
    if fmt == SchemaFormat.rng:
        errors = _validate_rng(xml_bytes, path)
    elif fmt == SchemaFormat.dtd:
        errors = _validate_dtd(xml_bytes, path)
    else:
        errors = _validate_xsd(xml_bytes, path)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


# ── HTTP download helper ───────────────────────────────────────────────────────

async def _fetch_url(url: str) -> bytes:
    """Download *url* with a size limit and timeout."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                total += len(chunk)
                if total > _MAX_IMPORT_BYTES:
                    raise DomainValidationError(
                        "FILE_TOO_LARGE",
                        f"Remote file exceeds the {_MAX_IMPORT_BYTES // (1024 * 1024)} MB limit.",
                    )
                chunks.append(chunk)
    return b"".join(chunks)


# ── CRUD ───────────────────────────────────────────────────────────────────────

async def list_schemas(db: AsyncSession) -> list[TeiSchemaResponse]:
    rows = list(await db.scalars(
        select(TeiSchema).order_by(TeiSchema.created_at.desc())
    ))
    return [TeiSchemaResponse.model_validate(r) for r in rows]


async def create_schema(
    db: AsyncSession, body: TeiSchemaCreate, actor: User
) -> TeiSchemaResponse:
    row = TeiSchema(name=body.name, created_by=actor.id)
    db.add(row)
    await db.flush()
    logger.info("tei_schema_created", name=body.name, actor=actor.username)
    return TeiSchemaResponse.model_validate(row)


async def _get_schema_or_404(db: AsyncSession, schema_id: uuid.UUID) -> TeiSchema:
    row = await db.get(TeiSchema, schema_id)
    if row is None:
        raise NotFoundError(f"Schema {schema_id} not found.")
    return row


async def delete_schema(db: AsyncSession, schema_id: uuid.UUID) -> None:
    row = await _get_schema_or_404(db, schema_id)
    # Remove files from disk (best-effort — DB row is deleted regardless)
    d = _schema_dir(schema_id)
    if d.exists():
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    await db.delete(row)
    logger.info("tei_schema_deleted", schema_id=str(schema_id))


# ── File upload / import ───────────────────────────────────────────────────────

def _detect_format(filename: str) -> SchemaFormat:
    ext = filename.rsplit(".", 1)[-1].lower()
    try:
        return SchemaFormat(ext)
    except ValueError:
        raise DomainValidationError(
            "INVALID_FORMAT",
            f"Unsupported schema format '.{ext}'. Allowed: rng, dtd, xsd.",
        )


async def upload_validation(
    db: AsyncSession,
    schema_id: uuid.UUID,
    filename: str,
    content: bytes,
) -> TeiSchemaResponse:
    row = await _get_schema_or_404(db, schema_id)
    fmt = _detect_format(filename)
    _ensure_schema_dir(schema_id)
    _validation_path(schema_id, fmt).write_bytes(content)
    row.validation_filename = filename
    row.validation_format = fmt
    await db.flush()
    return TeiSchemaResponse.model_validate(row)


async def import_validation(
    db: AsyncSession,
    schema_id: uuid.UUID,
    url: str,
) -> TeiSchemaResponse:
    _check_ssrf(url)
    filename = urlparse(url).path.rsplit("/", 1)[-1] or "schema"
    fmt = _detect_format(filename)
    try:
        content = await _fetch_url(url)
    except httpx.HTTPError as exc:
        raise ExternalServiceError("remote_schema", str(exc)) from exc
    return await upload_validation(db, schema_id, filename, content)


async def upload_cm5(
    db: AsyncSession,
    schema_id: uuid.UUID,
    filename: str,
    content: bytes,
) -> TeiSchemaResponse:
    row = await _get_schema_or_404(db, schema_id)
    _ensure_schema_dir(schema_id)
    _cm5_path(schema_id).write_bytes(content)
    row.cm5_filename = filename
    await db.flush()
    return TeiSchemaResponse.model_validate(row)


async def import_cm5(
    db: AsyncSession,
    schema_id: uuid.UUID,
    url: str,
) -> TeiSchemaResponse:
    _check_ssrf(url)
    filename = urlparse(url).path.rsplit("/", 1)[-1] or "cm5.xml"
    try:
        content = await _fetch_url(url)
    except httpx.HTTPError as exc:
        raise ExternalServiceError("remote_cm5_schema", str(exc)) from exc
    return await upload_cm5(db, schema_id, filename, content)


async def get_cm5_content(db: AsyncSession, schema_id: uuid.UUID) -> bytes:
    """Return the raw CM5 schema XML bytes for serving to the editor."""
    row = await _get_schema_or_404(db, schema_id)
    if not row.cm5_filename:
        raise NotFoundError("This schema has no CM5 autocomplete file.")
    path = _cm5_path(schema_id)
    if not path.exists():
        raise NotFoundError("CM5 schema file is missing on the server — please re-upload it.")
    return path.read_bytes()


# ── CM5 schema generation ──────────────────────────────────────────────────────
#
# Each _*_extract() function returns (top_element, elements) where:
#   top_element : str — the root TEI element name (e.g. "TEI")
#   elements    : dict[str, dict] — maps each element name to:
#                   {"children": list[str], "attrs": dict[str, list[str]]}
#
# _build_cm5_xml() serialises that structure to the <cm_tei_schema> XML format
# consumed by teiSchema.ts / CodeMirror 5 xml-hint.
# ──────────────────────────────────────────────────────────────────────────────

# ── RNG helpers ────────────────────────────────────────────────────────────────

def _rng_child_elements(
    node: etree._Element,  # type: ignore[name-defined]
    defines: dict[str, list[etree._Element]],  # type: ignore[name-defined]
    visited: frozenset[str],
) -> set[str]:
    """Return the set of element names reachable as children of *node*.

    Stops at ``<element>`` boundaries (their interior belongs to a different
    element's context).  Prevents cycles via the *visited* frozenset of
    already-expanded define names.
    """
    try:
        local = etree.QName(node.tag).localname
    except ValueError:
        return set()

    if local == "element":
        name = node.get("name", "")
        # Skip namespace-prefixed names (Schematron sch:rule, etc.)
        return {name} if name and ":" not in name else set()

    if local == "ref":
        ref_name = node.get("name", "")
        if not ref_name or ref_name in visited:
            return set()
        nv = visited | {ref_name}
        result: set[str] = set()
        for defn in defines.get(ref_name, []):
            for child in defn:
                result |= _rng_child_elements(child, defines, nv)
        return result

    # Leaf constructs that never contain element references
    if local in {"text", "data", "value", "empty", "notAllowed",
                 "param", "externalRef", "anyName", "nsName", "except"}:
        return set()

    # Structural wrappers: group, choice, optional, zeroOrMore, oneOrMore,
    # interleave, mixed — recurse into all children
    result: set[str] = set()
    for child in node:
        result |= _rng_child_elements(child, defines, visited)
    return result


def _rng_attrs(
    node: etree._Element,  # type: ignore[name-defined]
    defines: dict[str, list[etree._Element]],  # type: ignore[name-defined]
    visited: frozenset[str],
) -> dict[str, list[str]]:
    """Return {attr_name: [allowed_values]} reachable from *node*.

    Does not cross ``<element>`` boundaries (avoids collecting sibling
    element attributes as the parent's own attributes).
    """
    try:
        local = etree.QName(node.tag).localname
    except ValueError:
        return {}

    if local == "element":
        return {}  # stop — nested element's attrs are its own concern

    if local == "attribute":
        name = node.get("name", "")
        if not name:
            return {}
        values = [v.text or "" for v in node.iter(f"{{{_RNG_NS}}}value")]
        return {name: values}

    if local == "ref":
        ref_name = node.get("name", "")
        if not ref_name or ref_name in visited:
            return {}
        nv = visited | {ref_name}
        result: dict[str, list[str]] = {}
        for defn in defines.get(ref_name, []):
            for child in defn:
                for k, v in _rng_attrs(child, defines, nv).items():
                    result.setdefault(k, v)
        return result

    result: dict[str, list[str]] = {}
    for child in node:
        for k, v in _rng_attrs(child, defines, visited).items():
            result.setdefault(k, v)
    return result


def _rng_extract(path: Path) -> tuple[str, dict[str, dict]]:
    """Parse an RNG file and extract element → {children, attrs}."""
    tree = etree.parse(str(path), parser=_schema_xml_parser)
    root = tree.getroot()

    # Collect all <define> elements; handles combine="choice" by keeping all variants.
    defines: dict[str, list[etree._Element]] = {}  # type: ignore[name-defined]
    for defn in root.iter(f"{{{_RNG_NS}}}define"):
        name = defn.get("name")
        if name:
            defines.setdefault(name, []).append(defn)

    # Find every named <element> node across all defines.
    element_nodes: dict[str, list[etree._Element]] = {}  # type: ignore[name-defined]
    for defn_list in defines.values():
        for defn in defn_list:
            for el_node in defn.iter(f"{{{_RNG_NS}}}element"):
                name = el_node.get("name", "")
                if name and ":" not in name:
                    element_nodes.setdefault(name, []).append(el_node)

    elements: dict[str, dict] = {}
    for el_name, nodes in element_nodes.items():
        children: set[str] = set()
        attrs: dict[str, list[str]] = {}
        for node in nodes:
            for child in node:
                children |= _rng_child_elements(child, defines, frozenset())
                for k, v in _rng_attrs(child, defines, frozenset()).items():
                    attrs.setdefault(k, v)
        elements[el_name] = {
            "children": sorted(children),
            "attrs": attrs,
        }

    return _find_top(elements), elements


# ── XSD helpers ────────────────────────────────────────────────────────────────

def _xsd_child_elements(
    node: etree._Element,  # type: ignore[name-defined]
    groups: dict[str, etree._Element],  # type: ignore[name-defined]
    visited: frozenset[str],
) -> set[str]:
    """Return element names referenced (via ref=) inside XSD content model nodes."""
    try:
        local = etree.QName(node.tag).localname
    except ValueError:
        return set()

    if local == "element":
        ref = node.get("ref", "")
        # Strip namespace prefix (e.g. tei:p → p)
        return {ref.split(":")[-1]} if ref else set()

    if local == "group":
        ref = node.get("ref", "")
        if ref:
            key = ref.split(":")[-1]
            if key not in visited and key in groups:
                return _xsd_child_elements(groups[key], groups, visited | {key})
        return set()

    # Skip constructs that never contribute element children
    if local in {"annotation", "documentation", "appinfo",
                 "simpleType", "simpleContent", "attribute", "attributeGroup",
                 "anyAttribute"}:
        return set()

    result: set[str] = set()
    for child in node:
        result |= _xsd_child_elements(child, groups, visited)
    return result


def _xsd_attrs(
    node: etree._Element,  # type: ignore[name-defined]
    attr_groups: dict[str, etree._Element],  # type: ignore[name-defined]
    visited: frozenset[str],
) -> dict[str, list[str]]:
    """Return {attr_name: [allowed_values]} from XSD attribute / attributeGroup nodes."""
    try:
        local = etree.QName(node.tag).localname
    except ValueError:
        return {}

    if local == "attribute":
        name = node.get("name")
        if not name:
            return {}
        values = [e.get("value", "") for e in node.iter(f"{{{_XSD_NS}}}enumeration")]
        return {name: values}

    if local == "attributeGroup":
        ref = node.get("ref", "")
        if ref:
            key = ref.split(":")[-1]
            if key not in visited and key in attr_groups:
                return _xsd_attrs(attr_groups[key], attr_groups, visited | {key})
        return {}

    if local in {"annotation", "documentation", "appinfo", "simpleType"}:
        return {}

    result: dict[str, list[str]] = {}
    for child in node:
        for k, v in _xsd_attrs(child, attr_groups, visited).items():
            result.setdefault(k, v)
    return result


def _xsd_extract(path: Path) -> tuple[str, dict[str, dict]]:
    """Parse an XSD file and extract element → {children, attrs}."""
    tree = etree.parse(str(path), parser=_schema_xml_parser)
    root = tree.getroot()

    groups: dict[str, etree._Element] = {}  # type: ignore[name-defined]
    attr_groups: dict[str, etree._Element] = {}  # type: ignore[name-defined]
    top_level: list[tuple[str, etree._Element]] = []  # type: ignore[name-defined]

    for child in root:
        try:
            local = etree.QName(child.tag).localname
        except ValueError:
            continue
        name = child.get("name")
        if not name:
            continue
        if local == "group":
            groups[name] = child
        elif local == "attributeGroup":
            attr_groups[name] = child
        elif local == "element":
            top_level.append((name, child))

    elements: dict[str, dict] = {}
    for el_name, el_node in top_level:
        children: set[str] = set()
        attrs: dict[str, list[str]] = {}
        for sub in el_node:
            children |= _xsd_child_elements(sub, groups, frozenset({el_name}))
            for k, v in _xsd_attrs(sub, attr_groups, frozenset()).items():
                attrs.setdefault(k, v)
        elements[el_name] = {
            "children": sorted(children),
            "attrs": attrs,
        }

    return _find_top(elements), elements


# ── DTD helpers ────────────────────────────────────────────────────────────────

def _dtd_walk_content(node: object, result: set[str]) -> None:
    """Recursively collect element names from an lxml DTD ElementContent tree."""
    if node is None:
        return
    node_type = getattr(node, "type", None)
    if node_type == "element":
        name = getattr(node, "name", "")
        if name and name != "#PCDATA":
            result.add(name)
    elif node_type in ("seq", "or"):
        _dtd_walk_content(getattr(node, "left", None), result)
        _dtd_walk_content(getattr(node, "right", None), result)


def _dtd_extract(path: Path) -> tuple[str, dict[str, dict]]:
    """Parse a DTD file and extract element → {children, attrs}."""
    try:
        dtd = etree.DTD(file=str(path))
    except etree.LxmlError as exc:
        raise DomainValidationError("SCHEMA_PARSE_ERROR", f"DTD parse error: {exc}") from exc

    # Build element → attrs map in one pass over all attribute declarations.
    attrs_map: dict[str, dict[str, list[str]]] = {}
    for attr in dtd.attributes():
        values = list(attr.values()) if attr.type == "enumeration" else []
        attrs_map.setdefault(attr.elemname, {})[attr.name] = values

    elements: dict[str, dict] = {}
    for el_decl in dtd.elements():
        children: set[str] = set()
        _dtd_walk_content(el_decl.content, children)
        elements[el_decl.name] = {
            "children": sorted(children),
            "attrs": attrs_map.get(el_decl.name, {}),
        }

    return _find_top(elements), elements


# ── Shared utilities ───────────────────────────────────────────────────────────

def _find_top(elements: dict[str, dict]) -> str:
    """Return the top-level element name (the one not referenced by any other element)."""
    all_children: set[str] = set()
    for info in elements.values():
        all_children.update(info["children"])
    candidates = sorted(set(elements) - all_children)
    return candidates[0] if candidates else "TEI"


def _attr_qname(name: str) -> str | None:
    """Convert an attribute name to an lxml-safe form, or None if unsupported."""
    if name.startswith("xml:"):
        return f"{{{_XML_NS}}}{name[4:]}"
    if ":" in name:
        # Other namespace prefixes require explicit namespace declarations — skip.
        return None
    if not name or not (name[0].isalpha() or name[0] == "_"):
        return None
    return name


def _build_cm5_xml(top: str, elements: dict[str, dict]) -> bytes:
    """Serialise the extracted element map to the <cm_tei_schema> XML format."""
    root_el = etree.Element("cm_tei_schema")
    top_el = etree.SubElement(root_el, "top")
    top_el.text = top

    for tag_name in sorted(elements):
        info = elements[tag_name]
        try:
            el = etree.SubElement(root_el, tag_name)
        except (ValueError, TypeError):
            continue  # skip elements whose name is not a valid XML NCName

        for attr_name, values in sorted(info["attrs"].items()):
            qn = _attr_qname(attr_name)
            if qn is None:
                continue
            try:
                el.set(qn, ",".join(values) if values else "")
            except (ValueError, TypeError):
                pass

        if info["children"]:
            ch_el = etree.SubElement(el, "children")
            ch_el.text = ",".join(info["children"])

    return etree.tostring(root_el, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ── Service function ───────────────────────────────────────────────────────────

async def generate_cm5(db: AsyncSession, schema_id: uuid.UUID) -> TeiSchemaResponse:
    """Generate a CM5 autocomplete schema from the uploaded validation schema.

    Reads the already-stored RNG / XSD / DTD file, extracts element and
    attribute structure, and writes ``generated-cm5.xml`` to disk.  The
    schema record's ``cm5_filename`` is updated to point to the new file.

    Raises ``DomainValidationError`` if no validation file is attached or the
    file is missing on disk.
    """
    row = await _get_schema_or_404(db, schema_id)
    if not row.validation_filename or not row.validation_format:
        raise DomainValidationError(
            "NO_VALIDATION_FILE",
            "This schema has no validation file — upload one before generating CM5.",
        )
    path = _validation_path(schema_id, row.validation_format)
    if not path.exists():
        raise DomainValidationError(
            "MISSING_SCHEMA_FILE",
            "Validation schema file is missing on disk — please re-upload it.",
        )

    fmt = row.validation_format
    try:
        if fmt == SchemaFormat.rng:
            top, extracted = _rng_extract(path)
        elif fmt == SchemaFormat.xsd:
            top, extracted = _xsd_extract(path)
        else:
            top, extracted = _dtd_extract(path)
    except etree.LxmlError as exc:
        raise DomainValidationError(
            "SCHEMA_PARSE_ERROR",
            f"Could not parse the validation schema: {exc}",
        ) from exc

    logger.info(
        "cm5_generated",
        schema_id=str(schema_id),
        format=fmt.value,
        top=top,
        element_count=len(extracted),
    )
    cm5_bytes = _build_cm5_xml(top, extracted)
    return await upload_cm5(db, schema_id, "generated-cm5.xml", cm5_bytes)
