"""
xmldb — high-level service combining PostgreSQL metadata + eXist-db XML storage.

Pattern for write operations:
  1. All PostgreSQL mutations happen first (flushed, not committed).
  2. eXist-db operations happen after.
  3. If eXist-db raises → the exception propagates to the router's session
     context manager which rolls back the PostgreSQL transaction automatically.
  4. On success → the router commits after the service returns.

ACL is enforced here, not in the router layer, so that any caller
(router, future jobs, tests) gets consistent access control.
"""

import asyncio
import io
import os
import re
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Union

import xml.etree.ElementTree as _stdlib_ET

import defusedxml.ElementTree as _safe_xml

# Register TEI and xml: namespace prefixes so that ET.tostring() emits them
# correctly and never falls back to the ugly ns0:/ns1: fallback form.
_TEI_NS = "http://www.tei-c.org/ns/1.0"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_XML_ID = f"{{{_XML_NS}}}id"

_stdlib_ET.register_namespace("", _TEI_NS)
_stdlib_ET.register_namespace("xml", _XML_NS)
import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.core.hooks import HookEvent, hook_registry
from app.db.existdb import ExistDBClient
from app.core.constants import ROLE_LEVEL
from app.models.audit_log import AuditLog
from app.models.collection import Collection, CollectionStatus
from app.models.collection_permission import CollectionPermission
from app.models.notification import Notification
from app.models.role import Role, RoleName, UserRole
from app.models.user import User
from app.schemas.collections import (
    AssignAction,
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    DocumentInfo,
    DocumentMeta,
    PermissionEntry,
    PermissionGrant,
    PublicCollectionSearchResult,
    PublicDocHit,
    RejectAction,
    RespStmtItem,
    SearchHit,
    WorkflowAction,
    ZipUploadError,
    ZipUploadResult,
)

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


def _natural_sort_key(s: str) -> list[Union[int, str]]:
    """Sort key that orders numeric segments numerically.

    e.g. ['ara8.17.xml', 'ara8.61.xml', 'ara8.114.xml'] sorts correctly.
    """
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", s)]


# ── Filename validation ────────────────────────────────────────────────────────

_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-]*\.xml$")
_MAX_FILENAME_LEN = 128


def _validate_filename(filename: str) -> None:
    """Reject filenames that could cause path traversal or be non-XML."""
    if len(filename) > _MAX_FILENAME_LEN:
        raise DomainValidationError(
            "INVALID_FILENAME", f"Filename must be {_MAX_FILENAME_LEN} characters or fewer"
        )
    if not _FILENAME_RE.match(filename):
        raise DomainValidationError(
            "INVALID_FILENAME",
            "Filename must start with a letter or digit, contain only "
            "letters/digits/hyphens/underscores, and end with '.xml'",
        )


# ── ACL helpers ────────────────────────────────────────────────────────────────

def _level(role: str) -> int:
    return ROLE_LEVEL.get(role, 0)


async def _assert_read_access(
    db: AsyncSession, collection: Collection, actor: User, role: str
) -> None:
    """Raise AuthorizationError if the actor cannot read the collection.

    Access is granted when ANY of the following holds:
    - Actor has EditorInChief or Admin role (see all).
    - Collection is published (any authenticated user).
    - Actor is the assigned editor for the collection.
    - Actor has an explicit row in collection_permissions for this collection.
    """
    if _level(role) >= _level("EditorInChief"):
        return
    if collection.status == CollectionStatus.published:
        return
    if collection.editor_id == actor.id:
        return
    has_grant = await db.scalar(
        select(CollectionPermission).where(
            CollectionPermission.collection_id == collection.id,
            CollectionPermission.user_id == actor.id,
        )
    )
    if has_grant:
        return
    raise AuthorizationError("No access to this collection")


def _assert_write_access(collection: Collection, actor: User, role: str) -> None:
    """Raise if actor cannot modify documents in this collection.

    Published collections are frozen for everyone — the collection must be
    unpublished (returned to 'assigned' or 'review') before any document
    change is allowed.
    """
    if collection.status == CollectionStatus.published:
        raise AuthorizationError(
            "Collection is published — unpublish it before modifying documents"
        )
    if _level(role) >= _level("EditorInChief"):
        return
    if collection.editor_id != actor.id:
        raise AuthorizationError("No write access to this collection")
    if collection.status == CollectionStatus.review:
        raise AuthorizationError(
            "Collection is locked while under review — wait for EiC feedback"
        )
    if collection.status not in (CollectionStatus.assigned,):
        raise AuthorizationError("Collection is not in an editable state")


def _assert_eic(role: str) -> None:
    if _level(role) < _level("EditorInChief"):
        raise AuthorizationError("EditorInChief or Admin required")


def _assert_admin(role: str) -> None:
    if _level(role) < _level("Admin"):
        raise AuthorizationError("Admin required")


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _get_or_404(db: AsyncSession, collection_id: str) -> Collection:
    """Fetch a collection by UUID or slug; raise 404 if not found."""
    try:
        cid = uuid.UUID(collection_id)
        row = await db.get(Collection, cid)
    except ValueError:
        row = await db.scalar(select(Collection).where(Collection.slug == collection_id))
    if not row:
        raise NotFoundError("Collection not found")
    return row


def _audit(
    db: AsyncSession,
    action: str,
    actor: User,
    collection: Collection,
    payload: dict[str, object] | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="collection",
            target_id=str(collection.id),
            target_label=collection.title,
            payload=payload,
        )
    )


def _notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    body: str | None = None,
) -> None:
    db.add(
        Notification(user_id=user_id, type=type_, title=title, body=body)
    )


def _actor_label(actor: User) -> str:
    """Return the human-readable name of an actor for notification messages."""
    return actor.display_name or actor.username


async def _notify_broadcast_eic(
    db: AsyncSession,
    actor: User,
    type_: str,
    title: str,
    body: str | None = None,
) -> None:
    """Send a notification to every active EditorInChief and Admin, excluding the actor.

    Used for events (e.g. collection submitted for review) that all senior
    editors should be aware of regardless of who owns the collection.
    """
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            Role.name.in_([RoleName.EditorInChief, RoleName.Admin]),
            UserRole.revoked_at.is_(None),
            User.is_active.is_(True),
            User.id != actor.id,
        )
        .distinct()
    )
    for recipient in await db.scalars(stmt):
        _notify(db, recipient.id, type_, title, body)


# ── Collection CRUD ────────────────────────────────────────────────────────────

async def list_collections(
    db: AsyncSession,
    actor: User,
    role: str,
    page: int = 1,
    per_page: int = 20,
    status: CollectionStatus | None = None,
    search: str | None = None,
) -> tuple[list[CollectionResponse], int]:
    stmt = select(Collection)

    # Role-based visibility filter
    if _level(role) >= _level("EditorInChief"):
        pass  # see all
    elif role == "Editor":
        # Assigned collections + any collection where the editor has an explicit grant
        perm_sq = select(CollectionPermission.collection_id).where(
            CollectionPermission.user_id == actor.id
        )
        stmt = stmt.where(
            or_(Collection.editor_id == actor.id, Collection.id.in_(perm_sq))
        )
    else:
        # User / Designer: published collections + explicit permission grants
        perm_sq = select(CollectionPermission.collection_id).where(
            CollectionPermission.user_id == actor.id
        )
        stmt = stmt.where(
            or_(
                Collection.status == CollectionStatus.published,
                Collection.id.in_(perm_sq),
            )
        )

    if status:
        stmt = stmt.where(Collection.status == status)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(Collection.title.ilike(pattern), Collection.slug.ilike(pattern))
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(Collection.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    rows = list(await db.scalars(stmt))
    return [CollectionResponse.model_validate(r) for r in rows], total


async def get_collection(
    db: AsyncSession,
    collection_id: str,
    actor: User,
    role: str,
) -> CollectionResponse:
    col = await _get_or_404(db, collection_id)
    await _assert_read_access(db, col, actor, role)
    return CollectionResponse.model_validate(col)


async def create_collection(
    db: AsyncSession,
    existdb: ExistDBClient,
    body: CollectionCreate,
    actor: User,
    role: str,
) -> CollectionResponse:
    _assert_eic(role)

    existing = await db.scalar(select(Collection).where(Collection.slug == body.slug))
    if existing:
        raise ConflictError(f"Slug '{body.slug}' is already in use")

    col = Collection(
        slug=body.slug,
        title=body.title,
        description=body.description,
        is_public=body.is_public,
        owner_id=actor.id,
        status=CollectionStatus.draft,
    )
    db.add(col)
    await db.flush()  # get the UUID before hitting eXist-db

    # eXist-db — if this raises, the flush above is rolled back by the caller
    await existdb.create_collection(body.slug)

    _audit(db, "collection.created", actor, col, {"slug": body.slug})
    logger.info("collection_created", slug=body.slug, actor=actor.username)
    return CollectionResponse.model_validate(col)


async def update_collection(
    db: AsyncSession,
    collection_id: str,
    body: CollectionUpdate,
    actor: User,
    role: str,
) -> CollectionResponse:
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)

    changed: dict[str, object] = {}
    if body.title is not None:
        col.title = body.title
        changed["title"] = body.title
    if body.description is not None:
        col.description = body.description
        changed["description"] = body.description
    if body.is_public is not None and body.is_public != col.is_public:
        col.is_public = body.is_public
        changed["is_public"] = body.is_public
    if "schema_id" in body.model_fields_set:
        # None means "clear the schema"; a UUID means "attach this schema"
        if body.schema_id is not None:
            from app.models.tei_schema import TeiSchema as _TeiSchema
            if not await db.get(_TeiSchema, body.schema_id):
                raise NotFoundError(f"Schema {body.schema_id} not found.")
        col.schema_id = body.schema_id
        changed["schema_id"] = str(body.schema_id) if body.schema_id else None
    # Publication metadata — treat each field as "set when present in payload"
    if "publisher" in body.model_fields_set:
        col.publisher = body.publisher
        changed["publisher"] = body.publisher
    if "pub_place" in body.model_fields_set:
        col.pub_place = body.pub_place
        changed["pub_place"] = body.pub_place
    if "pub_year" in body.model_fields_set:
        col.pub_year = body.pub_year
        changed["pub_year"] = body.pub_year
    if "license_id" in body.model_fields_set:
        if body.license_id is not None:
            from app.models.license import License as _License
            if not await db.get(_License, body.license_id):
                raise NotFoundError(f"License {body.license_id} not found.")
        col.license_id = body.license_id
        changed["license_id"] = str(body.license_id) if body.license_id else None
    if "resp_stmts" in body.model_fields_set:
        col.resp_stmts = (
            [item.model_dump() for item in body.resp_stmts]
            if body.resp_stmts is not None
            else None
        )
        changed["resp_stmts"] = col.resp_stmts
    if "author" in body.model_fields_set:
        col.author = body.author
        changed["author"] = body.author
    if "listbibl_bibl_main" in body.model_fields_set:
        col.listbibl_bibl_main = body.listbibl_bibl_main
        changed["listbibl_bibl_main"] = body.listbibl_bibl_main
    if "msidentifier_idno" in body.model_fields_set:
        col.msidentifier_idno = body.msidentifier_idno
        changed["msidentifier_idno"] = body.msidentifier_idno
    if "objectdesc_form" in body.model_fields_set:
        col.objectdesc_form = body.objectdesc_form
        changed["objectdesc_form"] = body.objectdesc_form
    if "identifier_url" in body.model_fields_set:
        col.identifier_url = body.identifier_url
        changed["identifier_url"] = body.identifier_url
    if "body_template_id" in body.model_fields_set:
        if body.body_template_id is not None:
            from app.models.body_template import BodyTemplate as _BodyTemplate
            if not await db.get(_BodyTemplate, body.body_template_id):
                raise NotFoundError(f"Body template {body.body_template_id} not found.")
        col.body_template_id = body.body_template_id
        changed["body_template_id"] = str(body.body_template_id) if body.body_template_id else None
    if body.evt_enabled is not None and body.evt_enabled != col.evt_enabled:
        col.evt_enabled = body.evt_enabled
        changed["evt_enabled"] = body.evt_enabled

    if changed:
        _audit(db, "collection.updated", actor, col, changed)
    await db.flush()
    return CollectionResponse.model_validate(col)


async def delete_collection(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    actor: User,
    role: str,
) -> None:
    _assert_admin(role)
    col = await _get_or_404(db, collection_id)

    # eXist-db first — if it fails we abort before touching PostgreSQL
    await existdb.delete_collection(col.slug)

    _audit(db, "collection.deleted", actor, col)
    await db.flush()
    await db.delete(col)
    logger.info("collection_deleted", slug=col.slug, actor=actor.username)


# ── Workflow transitions ───────────────────────────────────────────────────────

async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if not user or user.deleted_at or not user.is_active:
        raise NotFoundError(f"User '{user_id}' not found or inactive")
    return user


async def assign_collection(
    db: AsyncSession,
    collection_id: str,
    body: AssignAction,
    actor: User,
    role: str,
) -> CollectionResponse:
    """Bozza → Assegnata (or reassign in Assegnata state)."""
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)

    if col.status not in (CollectionStatus.draft, CollectionStatus.assigned):
        raise ConflictError(
            f"Cannot assign: collection is in '{col.status.value}' state"
        )

    new_editor = await _get_user_or_404(db, body.user_id)
    is_reassign = col.editor_id is not None and col.editor_id != body.user_id

    # Notify old editor on reassignment
    if is_reassign and col.editor_id:
        _notify(
            db,
            col.editor_id,
            "collection.unassigned",
            f"{_actor_label(actor)} ti ha rimosso dall'assegnazione: {col.title}",
            body.note,
        )

    col.editor_id = new_editor.id
    col.status = CollectionStatus.assigned
    col.assigned_at = _now()

    action = "collection.reassigned" if is_reassign else "collection.assigned"
    _notify(
        db,
        new_editor.id,
        "collection.assigned",
        f"{_actor_label(actor)} ti ha assegnato: {col.title}",
        body.note,
    )
    _audit(db, action, actor, col, {"editor": new_editor.username, "note": body.note})
    await db.flush()
    logger.info(action, slug=col.slug, editor=new_editor.username)
    return CollectionResponse.model_validate(col)


async def submit_collection(
    db: AsyncSession,
    collection_id: str,
    body: WorkflowAction,
    actor: User,
    role: str,
) -> CollectionResponse:
    """Assegnata → Validazione (only the assigned editor)."""
    col = await _get_or_404(db, collection_id)

    if col.status != CollectionStatus.assigned:
        raise ConflictError("Collection must be in 'assigned' state to submit")
    if col.editor_id != actor.id:
        raise AuthorizationError("Only the assigned editor can submit for review")

    col.status = CollectionStatus.review
    col.submitted_at = _now()

    # Broadcast to all active EditorInChief and Admin users (excluding the actor).
    await _notify_broadcast_eic(
        db,
        actor,
        "collection.submitted",
        f"{_actor_label(actor)} ha inviato in validazione: {col.title}",
        body.note,
    )
    _audit(db, "collection.submitted", actor, col, {"note": body.note})
    await db.flush()
    await hook_registry.emit(HookEvent.ON_COLLECTION_SUBMITTED, collection=col)
    logger.info("collection_submitted", slug=col.slug, editor=actor.username)
    return CollectionResponse.model_validate(col)


async def reject_collection(
    db: AsyncSession,
    collection_id: str,
    body: RejectAction,
    actor: User,
    role: str,
) -> CollectionResponse:
    """Validazione → Assegnata (EiC/Admin sends back for revision)."""
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)

    if col.status != CollectionStatus.review:
        raise ConflictError("Collection must be in 'review' state to reject")

    col.status = CollectionStatus.assigned
    col.submitted_at = None  # reset — editor will re-submit

    if col.editor_id:
        _notify(
            db,
            col.editor_id,
            "collection.rejected",
            f"{_actor_label(actor)} ha rimandato in revisione: {col.title}",
            body.note,
        )
    _audit(db, "collection.rejected", actor, col, {"note": body.note})
    await db.flush()
    logger.info("collection_rejected", slug=col.slug, actor=actor.username)
    return CollectionResponse.model_validate(col)


async def publish_collection(
    db: AsyncSession,
    collection_id: str,
    body: WorkflowAction,
    actor: User,
    role: str,
) -> CollectionResponse:
    """Validazione → Pubblica."""
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)

    if col.status != CollectionStatus.review:
        raise ConflictError("Collection must be in 'review' state to publish")

    col.status = CollectionStatus.published
    col.published_at = _now()

    if col.editor_id:
        _notify(
            db,
            col.editor_id,
            "collection.published",
            f"{_actor_label(actor)} ha pubblicato: {col.title}",
            body.note,
        )
    _audit(db, "collection.published", actor, col, {"note": body.note})
    await db.flush()
    await hook_registry.emit(HookEvent.ON_COLLECTION_PUBLISHED, collection=col)
    logger.info("collection_published", slug=col.slug, actor=actor.username)
    return CollectionResponse.model_validate(col)


async def direct_publish_collection(
    db: AsyncSession,
    collection_id: str,
    body: WorkflowAction,
    actor: User,
    role: str,
) -> CollectionResponse:
    """Publish a collection directly from any status, bypassing the normal workflow.

    Restricted to EditorInChief and Admin. Emits ON_COLLECTION_PUBLISHED and
    notifies the assigned editor (if any), exactly as the regular publish path does.
    """
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)

    if col.status == CollectionStatus.published:
        raise ConflictError("Collection is already published")

    col.status = CollectionStatus.published
    col.published_at = _now()

    if col.editor_id:
        _notify(
            db,
            col.editor_id,
            "collection.published",
            f"{_actor_label(actor)} has directly published: {col.title}",
            body.note,
        )
    _audit(db, "collection.direct_published", actor, col, {"note": body.note})
    await db.flush()
    await hook_registry.emit(HookEvent.ON_COLLECTION_PUBLISHED, collection=col)
    logger.info("collection_direct_published", slug=col.slug, actor=actor.username)
    return CollectionResponse.model_validate(col)


async def unpublish_collection(
    db: AsyncSession,
    collection_id: str,
    body: WorkflowAction,
    actor: User,
    role: str,
) -> CollectionResponse:
    """Pubblica → Bozza (Admin only — destructive visibility change)."""
    _assert_admin(role)
    col = await _get_or_404(db, collection_id)

    if col.status != CollectionStatus.published:
        raise ConflictError("Collection must be in 'published' state to unpublish")

    col.status = CollectionStatus.draft
    col.published_at = None

    _audit(db, "collection.unpublished", actor, col, {"note": body.note})
    await db.flush()
    await hook_registry.emit(HookEvent.ON_COLLECTION_UNPUBLISHED, collection=col)
    logger.info("collection_unpublished", slug=col.slug, actor=actor.username)
    return CollectionResponse.model_validate(col)


# ── Document CRUD ──────────────────────────────────────────────────────────────

async def list_documents(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    actor: User,
    role: str,
) -> list[DocumentInfo]:
    """Return the list of XML documents stored in the collection on eXist-db."""
    col = await _get_or_404(db, collection_id)
    await _assert_read_access(db, col, actor, role)
    filenames = await existdb.list_collection(col.slug)
    filenames.sort(key=_natural_sort_key)
    return [DocumentInfo(filename=f) for f in filenames]


async def _sync_doc_count(
    db: AsyncSession, existdb: ExistDBClient, col: Collection
) -> None:
    """Refresh col.doc_count from eXist-db and flush the change (no commit)."""
    filenames = await existdb.list_collection(col.slug)
    col.doc_count = len(filenames)
    await db.flush()


async def upload_document(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    xml_bytes: bytes,
    actor: User,
    role: str,
) -> DocumentInfo:
    """Validate and store an XML document inside the collection on eXist-db.

    ACL: the assigned editor can upload only when the collection is in 'assigned'
    state. EiC and Admin are unrestricted.
    """
    col = await _get_or_404(db, collection_id)
    _assert_write_access(col, actor, role)
    _validate_filename(filename)

    # Validate well-formedness and guard against XXE before storing.
    try:
        _safe_xml.fromstring(xml_bytes)
    except Exception as exc:
        raise DomainValidationError("INVALID_XML", f"Document is not valid XML: {exc}") from exc

    await existdb.put_document(col.slug, filename, xml_bytes)
    await _sync_doc_count(db, existdb, col)
    _audit(
        db,
        "document.uploaded",
        actor,
        col,
        {"filename": filename, "size": len(xml_bytes)},
    )
    await hook_registry.emit(
        HookEvent.ON_DOCUMENT_UPLOADED, collection=col, filename=filename
    )
    logger.info("document_uploaded", slug=col.slug, filename=filename, actor=actor.username)
    return DocumentInfo(filename=filename)


async def update_document(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    xml_bytes: bytes,
    actor: User,
    role: str,
) -> DocumentInfo:
    """Overwrite an existing XML document with new content.

    The document must already exist in the collection. ACL rules are identical
    to upload: the assigned editor can edit only when the collection is in
    'assigned' state; EiC and Admin are unrestricted.
    """
    col = await _get_or_404(db, collection_id)
    _assert_write_access(col, actor, role)
    _validate_filename(filename)

    # Confirm the document exists before overwriting.
    existing = await existdb.list_collection(col.slug)
    if filename not in existing:
        raise NotFoundError(f"Document '{filename}' not found in collection '{col.slug}'")

    try:
        _safe_xml.fromstring(xml_bytes)
    except Exception as exc:
        raise DomainValidationError("INVALID_XML", f"Document is not valid XML: {exc}") from exc

    await existdb.put_document(col.slug, filename, xml_bytes)
    _audit(
        db,
        "document.updated",
        actor,
        col,
        {"filename": filename, "size": len(xml_bytes)},
    )
    logger.info("document_updated", slug=col.slug, filename=filename, actor=actor.username)
    return DocumentInfo(filename=filename)


async def download_document(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    actor: User,
    role: str,
) -> bytes:
    """Retrieve raw XML bytes for a document stored in eXist-db."""
    col = await _get_or_404(db, collection_id)
    await _assert_read_access(db, col, actor, role)
    _validate_filename(filename)
    return await existdb.get_document(col.slug, filename)


async def delete_document(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    actor: User,
    role: str,
) -> None:
    """Delete a document from eXist-db.

    ACL: same write-access rules as upload (assigned editor, not in review).
    """
    col = await _get_or_404(db, collection_id)
    _assert_write_access(col, actor, role)
    _validate_filename(filename)
    await existdb.delete_document(col.slug, filename)
    await _sync_doc_count(db, existdb, col)
    _audit(db, "document.deleted", actor, col, {"filename": filename})
    await hook_registry.emit(
        HookEvent.ON_DOCUMENT_DELETED, collection=col, filename=filename
    )
    logger.info("document_deleted", slug=col.slug, filename=filename, actor=actor.username)


async def upload_zip_batch(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    zip_bytes: bytes,
    actor: User,
    role: str,
) -> ZipUploadResult:
    """Extract an uploaded ZIP archive and store each valid XML file in eXist-db.

    Limits are read from system_settings at call time so an Admin can adjust
    them without restarting the server:
      - zip_max_size_mb       raw ZIP size ceiling
      - zip_max_extracted_mb  total decompressed size ceiling (zip-bomb guard)
      - zip_max_files         maximum number of XML members processed

    Files that fail filename validation or XML well-formedness are recorded in
    ``errors`` and do not abort the batch. Non-XML members and entries inside
    subdirectories are silently recorded in ``skipped``.
    """
    from app.models.system_setting import SystemSetting

    col = await _get_or_404(db, collection_id)
    _assert_write_access(col, actor, role)

    async def _setting(key: str, default: int) -> int:
        row = await db.get(SystemSetting, key)
        try:
            return int(row.value) if row else default
        except (ValueError, AttributeError):
            return default

    max_size_mb = await _setting("zip_max_size_mb", 50)
    max_extracted_mb = await _setting("zip_max_extracted_mb", 200)
    max_files = await _setting("zip_max_files", 500)

    if len(zip_bytes) > max_size_mb * 1024 * 1024:
        raise DomainValidationError(
            "ZIP_TOO_LARGE",
            f"ZIP archive exceeds the {max_size_mb} MB size limit",
        )

    if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
        raise DomainValidationError("INVALID_ZIP", "Uploaded file is not a valid ZIP archive")

    uploaded = 0
    skipped: list[str] = []
    errors: list[ZipUploadError] = []
    total_extracted = 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]

        for member in members:
            # Use basename only — never follow subdirectory paths.
            basename = os.path.basename(member.filename)

            # Skip non-XML and entries that live inside subdirectories.
            if not basename.lower().endswith(".xml"):
                skipped.append(member.filename)
                continue
            if basename != member.filename.lstrip("/"):
                # File is inside a subdirectory inside the ZIP.
                skipped.append(member.filename)
                continue

            if uploaded + len(errors) >= max_files:
                raise DomainValidationError(
                    "ZIP_TOO_MANY_FILES",
                    f"ZIP archive contains more than {max_files} XML files",
                )

            try:
                _validate_filename(basename)
            except DomainValidationError as exc:
                errors.append(ZipUploadError(filename=basename, error=exc.message))
                continue

            # Zip-bomb guard: stream decompression and measure actual bytes.
            # member.file_size is the declared size in the ZIP central directory
            # and can be falsified.  We count real decompressed bytes instead.
            limit = max_extracted_mb * 1024 * 1024
            buf = io.BytesIO()
            with zf.open(member.filename) as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    buf.write(chunk)
                    total_extracted += len(chunk)
                    if total_extracted > limit:
                        raise DomainValidationError(
                            "ZIP_EXTRACTED_TOO_LARGE",
                            f"Total uncompressed size exceeds the {max_extracted_mb} MB limit",
                        )
            xml_bytes = buf.getvalue()
            try:
                _safe_xml.fromstring(xml_bytes)
            except Exception as exc:
                errors.append(ZipUploadError(filename=basename, error=f"Invalid XML: {exc}"))
                continue
            await existdb.put_document(col.slug, basename, xml_bytes)
            uploaded += 1

    await _sync_doc_count(db, existdb, col)
    _audit(
        db,
        "document.zip_uploaded",
        actor,
        col,
        {"uploaded": uploaded, "skipped": len(skipped), "errors": len(errors)},
    )
    logger.info(
        "zip_batch_uploaded",
        slug=col.slug,
        uploaded=uploaded,
        skipped=len(skipped),
        errors=len(errors),
        actor=actor.username,
    )
    return ZipUploadResult(uploaded=uploaded, skipped=skipped, errors=errors)


# ── Collection permission management ──────────────────────────────────────────

async def list_permissions(
    db: AsyncSession,
    collection_id: str,
    actor: User,
    role: str,
) -> list[PermissionEntry]:
    """Return all explicit permission grants for the collection. EiC/Admin only."""
    _assert_eic(role)
    await _get_or_404(db, collection_id)  # 404 if collection does not exist
    rows = list(
        await db.scalars(
            select(CollectionPermission).where(
                CollectionPermission.collection_id == collection_id
            )
        )
    )
    return [PermissionEntry.model_validate(r) for r in rows]


async def grant_permission(
    db: AsyncSession,
    collection_id: str,
    body: PermissionGrant,
    actor: User,
    role: str,
) -> PermissionEntry:
    """Grant a user explicit read access to the collection. EiC/Admin only.

    Idempotent: if the grant already exists it is returned as-is.
    """
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)
    target_user = await _get_user_or_404(db, body.user_id)

    existing = await db.get(
        CollectionPermission, {"collection_id": collection_id, "user_id": target_user.id}
    )
    if existing:
        return PermissionEntry.model_validate(existing)

    perm = CollectionPermission(
        collection_id=collection_id,
        user_id=target_user.id,
        granted_by_id=actor.id,
    )
    db.add(perm)
    _audit(
        db,
        "collection.permission_granted",
        actor,
        col,
        {"target_user": target_user.username},
    )
    await db.flush()
    logger.info(
        "collection_permission_granted",
        slug=col.slug,
        target=target_user.username,
        actor=actor.username,
    )
    return PermissionEntry.model_validate(perm)


async def revoke_permission(
    db: AsyncSession,
    collection_id: str,
    user_id: uuid.UUID,
    actor: User,
    role: str,
) -> None:
    """Revoke a user's explicit read access to the collection. EiC/Admin only."""
    _assert_eic(role)
    col = await _get_or_404(db, collection_id)

    perm = await db.get(
        CollectionPermission, {"collection_id": collection_id, "user_id": user_id}
    )
    if not perm:
        raise NotFoundError("Permission grant not found")

    target_user = await db.get(User, user_id)
    username = target_user.username if target_user else str(user_id)

    _audit(
        db,
        "collection.permission_revoked",
        actor,
        col,
        {"target_user": username},
    )
    await db.delete(perm)
    await db.flush()
    logger.info(
        "collection_permission_revoked",
        slug=col.slug,
        target=username,
        actor=actor.username,
    )


# ── XQuery operations ──────────────────────────────────────────────────────────

_DEFAULT_MAX_SEARCH_RESULTS = 50


async def search_in_collection(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    query: str,
    actor: User,
    role: str,
    max_results: int = _DEFAULT_MAX_SEARCH_RESULTS,
) -> list[SearchHit]:
    """Case-insensitive full-text search across documents in a collection.

    Uses XQuery contains() — no Lucene index required.
    Returns up to *max_results* hits ordered by document iteration order.
    """
    col = await _get_or_404(db, collection_id)
    await _assert_read_access(db, col, actor, role)

    raw = await existdb.xquery(
        "search/fulltext_collection.xq",
        {
            "collection_path": existdb.col_path(col.slug),
            "query": query,
            "max_results": str(max_results),
        },
    )
    root = _safe_xml.fromstring(raw)
    return [
        SearchHit(
            filename=hit.get("filename", ""),
            snippet=hit.get("snippet", ""),
        )
        for hit in root.findall("hit")
    ]


async def search_public_collections(
    db: AsyncSession,
    existdb: ExistDBClient,
    query: str,
    max_doc_hits: int = 3,
) -> list[PublicCollectionSearchResult]:
    """Search across all published+public collections (metadata + document content).

    Metadata match: query is a case-insensitive substring of the collection title or slug.
    Content match: XQuery contains() across document text nodes.

    Collections are fetched once from PostgreSQL; eXist-db queries run in parallel
    via asyncio.gather.  Up to *max_doc_hits* snippet hits are returned per collection.
    """
    stmt = (
        select(Collection)
        .where(
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
        .order_by(Collection.published_at.desc())
        .limit(200)
    )
    rows = list(await db.scalars(stmt))

    async def _search_col(col: Collection) -> tuple[Collection, list[PublicDocHit]]:
        try:
            raw = await existdb.xquery(
                "search/fulltext_collection.xq",
                {
                    "collection_path": existdb.col_path(col.slug),
                    "query": query,
                    "max_results": str(max_doc_hits),
                },
            )
            root = _safe_xml.fromstring(raw)
            return col, [
                PublicDocHit(filename=h.get("filename", ""), snippet=h.get("snippet", ""))
                for h in root.findall("hit")
            ]
        except Exception:
            return col, []

    pairs = await asyncio.gather(*[_search_col(c) for c in rows])
    q_lower = query.lower()
    results: list[PublicCollectionSearchResult] = []
    for col, hits in pairs:
        title_match = q_lower in col.title.lower() or q_lower in col.slug.lower()
        if title_match or hits:
            results.append(
                PublicCollectionSearchResult(
                    collection=CollectionResponse.model_validate(col),
                    doc_hits=hits,
                )
            )
    return results


async def get_document_metadata(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    actor: User,
    role: str,
) -> DocumentMeta:
    """Return generic XML metadata for a document stored in eXist-db.

    Extracted via XQuery: root element name, namespace URI, character size,
    and direct child count. Does not parse TEI-specific fields.
    """
    col = await _get_or_404(db, collection_id)
    await _assert_read_access(db, col, actor, role)
    _validate_filename(filename)

    doc_path = f"{existdb.col_path(col.slug)}/{filename}"
    raw = await existdb.xquery(
        "documents/get_metadata.xq",
        {"doc_path": doc_path},
    )
    root = _safe_xml.fromstring(raw)
    return DocumentMeta(
        root_element=root.findtext("root-element") or "",
        namespace=root.findtext("namespace") or "",
        size=int(root.findtext("size") or 0),
        child_count=int(root.findtext("child-count") or 0),
    )


async def validate_document(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    actor: User,
    role: str,
    xml_content: str | None = None,
) -> "ValidationResult":
    """Validate an XML document against the TEI schema attached to its collection.

    Requires the collection to have a schema with a validation file.
    Validation failure is non-blocking: this function always returns a
    ValidationResult; it never raises on schema errors.

    When *xml_content* is provided it is validated directly; otherwise the
    saved document is fetched from eXist-db.  Pass the editor buffer here to
    validate unsaved changes without requiring a save first.

    Raises NotFoundError if the collection, document, or schema is missing.
    Raises DomainValidationError if the schema has no validation file attached.
    """
    from app.models.tei_schema import TeiSchema as _TeiSchema
    from app.schemas.tei_schemas import ValidationResult
    from app.services.schemas import validate_xml

    col = await _get_or_404(db, collection_id)
    await _assert_read_access(db, col, actor, role)
    _validate_filename(filename)

    if not col.schema_id:
        raise DomainValidationError(
            "NO_SCHEMA",
            "This collection has no TEI schema attached. Assign a schema first.",
        )
    schema = await db.get(_TeiSchema, col.schema_id)
    if schema is None:
        raise NotFoundError("The schema attached to this collection no longer exists.")

    if xml_content is not None:
        xml_bytes = xml_content.encode("utf-8")
    else:
        xml_bytes = await existdb.get_document(col.slug, filename)

    return validate_xml(xml_bytes, schema)


# ── Zone helpers ───────────────────────────────────────────────────────────────


def _reserialise(original_bytes: bytes, root: _stdlib_ET.Element) -> bytes:
    """Rebuild an XML byte string from a mutated ElementTree root.

    Preserves the original ``<?xml … ?>`` declaration when present; omits it
    when the original had none (common for documents stored directly in eXist-db
    without a processing instruction).

    ``register_namespace`` is called immediately before ``tostring`` — not just
    at module load — so the TEI default-namespace mapping is guaranteed to be in
    effect even if another FastAPI dependency has overwritten the global
    ``_namespace_map`` between import time and request handling.  This is safe
    inside an async event loop because all synchronous code runs on a single
    thread; no other coroutine can interleave during a plain function call.
    """
    _stdlib_ET.register_namespace("", _TEI_NS)
    _stdlib_ET.register_namespace("xml", _XML_NS)

    m = re.match(rb"(<\?xml[^?]*\?>)", original_bytes.lstrip())
    decl = (m.group(1).decode("utf-8") + "\n") if m else ""
    body = _stdlib_ET.tostring(root, encoding="unicode")
    return (decl + body).encode("utf-8")


def _find_surface(
    root: _stdlib_ET.Element, surface_id: str
) -> _stdlib_ET.Element | None:
    """Return the ``<surface xml:id='{surface_id}'>`` element or *None*."""
    facs = root.find(f"{{{_TEI_NS}}}facsimile")
    if facs is None:
        return None
    for surface in facs.findall(f"{{{_TEI_NS}}}surface"):
        if surface.get(_XML_ID) == surface_id:
            return surface
    return None


# ── Zone service functions ─────────────────────────────────────────────────────


async def get_surface_zones(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    surface_id: str,
    actor: User,
    role: str,
) -> "SurfaceZonesResponse":
    """Return all ``<zone>`` elements for a ``<surface>`` in a TEI document.

    Returns an empty zone list when the document has no ``<facsimile>`` block.
    Raises ``NotFoundError`` when the surface ``xml:id`` does not exist.
    """
    from app.schemas.facsimile import SurfaceZonesResponse, ZoneOut

    col = await _get_or_404(db, collection_id)
    await _assert_read_access(db, col, actor, role)
    _validate_filename(filename)

    xml_bytes = await existdb.get_document(col.slug, filename)

    try:
        root = _safe_xml.fromstring(xml_bytes)
    except Exception as exc:
        raise DomainValidationError("INVALID_XML", "Document is not well-formed XML") from exc

    facs = root.find(f"{{{_TEI_NS}}}facsimile")
    if facs is None:
        # No facsimile block — treat as zero zones rather than 404.
        return SurfaceZonesResponse(surface_id=surface_id, zones=[])

    surface = _find_surface(root, surface_id)
    if surface is None:
        raise NotFoundError(f"Surface '{surface_id}' not found in document facsimile")

    zones: list[ZoneOut] = []
    for zone_el in surface.findall(f"{{{_TEI_NS}}}zone"):
        z_id = zone_el.get(_XML_ID, "")
        try:
            zones.append(
                ZoneOut(
                    xml_id=z_id,
                    ulx=int(zone_el.get("ulx", 0)),
                    uly=int(zone_el.get("uly", 0)),
                    lrx=int(zone_el.get("lrx", 0)),
                    lry=int(zone_el.get("lry", 0)),
                )
            )
        except (ValueError, TypeError):
            # Skip malformed zone elements rather than crashing.
            logger.warning("zone.malformed", surface_id=surface_id, zone_id=z_id)

    return SurfaceZonesResponse(surface_id=surface_id, zones=zones)


async def update_surface_zones(
    db: AsyncSession,
    existdb: ExistDBClient,
    collection_id: str,
    filename: str,
    surface_id: str,
    zones: list["ZoneIn"],
    actor: User,
    role: str,
) -> "SurfaceZonesResponse":
    """Replace all ``<zone>`` children of a ``<surface>`` atomically.

    Sending an empty *zones* list removes all existing zones.
    Raises ``NotFoundError`` when the surface does not exist (creating surfaces
    is the responsibility of the media/facsimile panel, not this endpoint).
    """
    from app.schemas.facsimile import SurfaceZonesResponse, ZoneOut

    col = await _get_or_404(db, collection_id)
    _assert_write_access(col, actor, role)
    _validate_filename(filename)

    xml_bytes = await existdb.get_document(col.slug, filename)

    try:
        root = _safe_xml.fromstring(xml_bytes)
    except Exception as exc:
        raise DomainValidationError("INVALID_XML", "Document is not well-formed XML") from exc

    surface = _find_surface(root, surface_id)
    if surface is None:
        raise NotFoundError(f"Surface '{surface_id}' not found in document facsimile")

    # Remove all existing <zone> children.
    for zone_el in surface.findall(f"{{{_TEI_NS}}}zone"):
        surface.remove(zone_el)

    # Append new zones in the order provided by the caller.
    zone_outs: list[ZoneOut] = []
    for z in zones:
        zone_el = _stdlib_ET.SubElement(surface, f"{{{_TEI_NS}}}zone")
        zone_el.set(_XML_ID, z.xml_id)
        zone_el.set("ulx", str(z.ulx))
        zone_el.set("uly", str(z.uly))
        zone_el.set("lrx", str(z.lrx))
        zone_el.set("lry", str(z.lry))
        zone_outs.append(ZoneOut(xml_id=z.xml_id, ulx=z.ulx, uly=z.uly, lrx=z.lrx, lry=z.lry))

    new_bytes = _reserialise(xml_bytes, root)
    await existdb.put_document(col.slug, filename, new_bytes)

    _audit(
        db,
        "document.zones_updated",
        actor,
        col,
        {"filename": filename, "surface_id": surface_id, "zone_count": len(zones)},
    )

    return SurfaceZonesResponse(surface_id=surface_id, zones=zone_outs)
