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

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
)
from app.db.existdb import ExistDBClient
from app.middleware.acl import ROLE_LEVEL
from app.models.audit_log import AuditLog
from app.models.collection import Collection, CollectionStatus
from app.models.notification import Notification
from app.models.user import User
from app.schemas.collections import (
    AssignAction,
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    RejectAction,
    WorkflowAction,
)

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


# ── ACL helpers ────────────────────────────────────────────────────────────────

def _level(role: str) -> int:
    return ROLE_LEVEL.get(role, 0)


def _assert_read_access(collection: Collection, actor: User, role: str) -> None:
    if _level(role) >= _level("EditorInChief"):
        return
    if collection.status == CollectionStatus.published:
        return  # published collections are readable by any authenticated user
    if collection.editor_id == actor.id:
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

async def _get_or_404(db: AsyncSession, collection_id: uuid.UUID) -> Collection:
    row = await db.get(Collection, collection_id)
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
        stmt = stmt.where(Collection.editor_id == actor.id)
    else:
        # User role: only published collections
        stmt = stmt.where(Collection.status == CollectionStatus.published)

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
    collection_id: uuid.UUID,
    actor: User,
    role: str,
) -> CollectionResponse:
    col = await _get_or_404(db, collection_id)
    _assert_read_access(col, actor, role)
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
    collection_id: uuid.UUID,
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
    collection_id: uuid.UUID,
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
    collection_id: uuid.UUID,
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
    collection_id: uuid.UUID,
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
    collection_id: uuid.UUID,
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
    collection_id: uuid.UUID,
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
    collection_id: uuid.UUID,
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
