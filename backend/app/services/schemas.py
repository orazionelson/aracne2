"""
schemas — TEI schema management service.

Handles file storage, URL import (with SSRF guard), and XML validation
against RNG / DTD / XSD schemas using lxml.

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
