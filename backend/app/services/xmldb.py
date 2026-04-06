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

import re
import uuid
from datetime import UTC, datetime

import defusedxml.ElementTree as _safe_xml
import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.db.existdb import ExistDBClient
from app.middleware.acl import ROLE_LEVEL
from app.models.audit_log import AuditLog
from app.models.collection import Collection, CollectionStatus
from app.models.collection_permission import CollectionPermission
from app.models.notification import Notification
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
    RejectAction,
    SearchHit,
    WorkflowAction,
)

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


# ── Filename validation ────────────────────────────────────────────────────────

_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*\.xml$")
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
    """Raise if actor cannot modify documents in this collection."""
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
            f"Rimosso dall'assegnazione: {col.title}",
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
        f"Nuova collezione assegnata: {col.title}",
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

    # Notify the collection owner (EiC/Admin who created it)
    if col.owner_id:
        _notify(
            db,
            col.owner_id,
            "collection.submitted",
            f"Collezione in revisione: {col.title}",
            body.note,
        )
    _audit(db, "collection.submitted", actor, col, {"note": body.note})
    await db.flush()
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
            f"Revisione richiesta: {col.title}",
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
            f"Collezione pubblicata: {col.title}",
            body.note,
        )
    _audit(db, "collection.published", actor, col, {"note": body.note})
    await db.flush()
    logger.info("collection_published", slug=col.slug, actor=actor.username)
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
    return [DocumentInfo(filename=f) for f in filenames]


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
    _audit(
        db,
        "document.uploaded",
        actor,
        col,
        {"filename": filename, "size": len(xml_bytes)},
    )
    logger.info("document_uploaded", slug=col.slug, filename=filename, actor=actor.username)
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
    _audit(db, "document.deleted", actor, col, {"filename": filename})
    logger.info("document_deleted", slug=col.slug, filename=filename, actor=actor.username)


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
