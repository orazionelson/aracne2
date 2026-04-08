"""
Collections plugin router.

Endpoints are split into three groups declared in this order to avoid
path conflicts:
  1. /collections/public  — unauthenticated public listing
  2. /collections         — authenticated CRUD + workflow
  3. /collections/{id}/…  — per-collection sub-routes
"""

import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.middleware.acl import ROLE_LEVEL, get_current_user, require_role
from app.models.collection import CollectionStatus
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
    RejectAction,
    SearchHit,
    WorkflowAction,
    ZipUploadResult,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.collection_validation import CollectionValidationRunResponse
from app.schemas.tei_schemas import ValidationResult
from app.services.collection_validation import (
    cancel_validation_run,
    get_latest_validation_run,
    get_validation_run,
    start_validation_run,
)
from app.services.xmldb import (
    assign_collection,
    create_collection,
    delete_collection,
    delete_document,
    download_document,
    get_collection,
    get_document_metadata,
    grant_permission,
    list_collections,
    list_documents,
    list_permissions,
    publish_collection,
    reject_collection,
    revoke_permission,
    search_in_collection,
    search_public_collections,
    submit_collection,
    unpublish_collection,
    update_collection,
    update_document,
    upload_document,
    upload_zip_batch,
    validate_document,
)

router = APIRouter(prefix="/collections", tags=["collections"])

_auth = Depends(get_current_user)
_eic = Depends(require_role(min_role="EditorInChief"))
_admin = Depends(require_role(min_role="Admin"))


# ── Public endpoint (no auth) ─────────────────────────────────────────────────

@router.get("/public")
async def collections_public(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
) -> PaginatedResponse[CollectionResponse]:
    """List published + is_public collections. No authentication required."""
    from sqlalchemy import func, or_, select
    from app.models.collection import Collection

    stmt = select(Collection).where(
        Collection.status == CollectionStatus.published,
        Collection.is_public.is_(True),
    )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(Collection.title.ilike(pattern), Collection.slug.ilike(pattern))
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(await db.scalars(
        stmt.order_by(Collection.published_at.desc())
            .offset((page - 1) * per_page).limit(per_page)
    ))
    return PaginatedResponse(
        data=[CollectionResponse.model_validate(r) for r in rows],
        pagination=PaginationMeta(
            page=page, per_page=per_page, total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


@router.get("/public/search")
async def collections_public_search(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
    q: str = Query(min_length=1, max_length=256),
    max_doc_hits: int = Query(default=3, ge=1, le=10),
) -> DataResponse[list[PublicCollectionSearchResult]]:
    """Search published public collections by title/slug and document content.

    No authentication required. Results include collections matched by metadata
    and collections where the query appears in document text, with short snippets.
    """
    results = await search_public_collections(db, existdb, q, max_doc_hits)
    return DataResponse(data=results)


# ── Authenticated CRUD ────────────────────────────────────────────────────────

@router.get("")
async def collections_list(
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: CollectionStatus | None = Query(default=None),
    search: str | None = Query(default=None),
) -> PaginatedResponse[CollectionResponse]:
    role: str = request.state.role
    items, total = await list_collections(db, current_user, role, page, per_page, status, search)
    return PaginatedResponse(
        data=items,
        pagination=PaginationMeta(
            page=page, per_page=per_page, total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


@router.post("", status_code=201)
async def collection_create(
    request: Request,
    body: CollectionCreate,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await create_collection(db, existdb, body, current_user, role)
    return DataResponse(data=data)


@router.get("/{collection_id}")
async def collection_detail(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await get_collection(db, collection_id, current_user, role)
    return DataResponse(data=data)


@router.patch("/{collection_id}")
async def collection_update(
    collection_id: str,
    body: CollectionUpdate,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await update_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.delete("/{collection_id}", status_code=204)
async def collection_delete(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> None:
    role: str = request.state.role
    await delete_collection(db, existdb, collection_id, current_user, role)


# ── Workflow transitions ───────────────────────────────────────────────────────

@router.post("/{collection_id}/assign")
async def collection_assign(
    collection_id: str,
    body: AssignAction,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await assign_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/submit")
async def collection_submit(
    collection_id: str,
    body: WorkflowAction,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await submit_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/reject")
async def collection_reject(
    collection_id: str,
    body: RejectAction,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await reject_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/publish")
async def collection_publish(
    collection_id: str,
    body: WorkflowAction,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await publish_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/unpublish")
async def collection_unpublish(
    collection_id: str,
    body: WorkflowAction,
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await unpublish_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


# ── Document CRUD ─────────────────────────────────────────────────────────────

@router.get("/{collection_id}/documents")
async def document_list(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[list[DocumentInfo]]:
    """List all XML documents in the collection stored on eXist-db."""
    role: str = request.state.role
    docs = await list_documents(db, existdb, collection_id, current_user, role)
    return DataResponse(data=docs)


@router.post("/{collection_id}/documents", status_code=201)
async def document_upload(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
    file: UploadFile,
) -> DataResponse[DocumentInfo]:
    """Upload (or overwrite) an XML document.

    The multipart field must be named ``file``.
    The original filename is used as the document name in eXist-db and must
    match ``^[a-zA-Z0-9][a-zA-Z0-9_\\-]*\\.xml$``.
    """
    role: str = request.state.role
    filename = file.filename or ""
    xml_bytes = await file.read()
    doc = await upload_document(
        db, existdb, collection_id, filename, xml_bytes, current_user, role
    )
    return DataResponse(data=doc)


@router.post("/{collection_id}/documents/batch", status_code=201)
async def document_upload_zip(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
    file: UploadFile,
) -> DataResponse[ZipUploadResult]:
    """Upload a ZIP archive and store every valid XML file inside the collection.

    The multipart field must be named ``file`` and the uploaded file must be a
    valid ZIP archive (.zip). Files inside subdirectories are skipped. Each XML
    member's filename is validated against the same rules as single-file upload.

    Limits (configurable via system_settings):
    - zip_max_size_mb: maximum raw ZIP size
    - zip_max_extracted_mb: maximum total decompressed size (zip-bomb guard)
    - zip_max_files: maximum number of XML files processed per request
    """
    role: str = request.state.role
    zip_bytes = await file.read()
    result = await upload_zip_batch(
        db, existdb, collection_id, zip_bytes, current_user, role
    )
    return DataResponse(data=result)


@router.put("/{collection_id}/documents/{filename}")
async def document_update(
    collection_id: str,
    filename: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[DocumentInfo]:
    """Overwrite an existing XML document with raw XML from the request body.

    Content-Type must be ``application/xml`` or ``text/xml``.
    The document must already exist in the collection.
    """
    role: str = request.state.role
    xml_bytes = await request.body()
    doc = await update_document(
        db, existdb, collection_id, filename, xml_bytes, current_user, role
    )
    return DataResponse(data=doc)


@router.get("/{collection_id}/documents/{filename}")
async def document_download(
    collection_id: str,
    filename: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> Response:
    """Download the raw XML bytes of a document."""
    role: str = request.state.role
    xml_bytes = await download_document(
        db, existdb, collection_id, filename, current_user, role
    )
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{collection_id}/documents/{filename}", status_code=204)
async def document_delete(
    collection_id: str,
    filename: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> None:
    """Delete a document from the collection."""
    role: str = request.state.role
    await delete_document(db, existdb, collection_id, filename, current_user, role)


# ── XQuery operations ─────────────────────────────────────────────────────────

@router.get("/{collection_id}/search")
async def collection_search(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
    q: str = Query(min_length=1, max_length=256),
    max_results: int = Query(default=50, ge=1, le=200),
) -> DataResponse[list[SearchHit]]:
    """Case-insensitive full-text search across all documents in a collection.

    Returns up to *max_results* hits, each with the matching document's filename
    and a short text snippet around the first occurrence of the query term.
    """
    role: str = request.state.role
    hits = await search_in_collection(
        db, existdb, collection_id, q, current_user, role, max_results
    )
    return DataResponse(data=hits)


@router.get("/{collection_id}/documents/{filename}/metadata")
async def document_metadata(
    collection_id: str,
    filename: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[DocumentMeta]:
    """Return generic XML metadata for a document extracted via XQuery.

    Reports the root element name, its namespace URI, the total character
    size of the serialized document, and the count of direct child elements.
    """
    role: str = request.state.role
    meta = await get_document_metadata(
        db, existdb, collection_id, filename, current_user, role
    )
    return DataResponse(data=meta)


# ── Permission management ─────────────────────────────────────────────────────

@router.get("/{collection_id}/permissions")
async def permission_list(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[PermissionEntry]]:
    """List all explicit read-access grants for a collection. EditorInChief+ only."""
    role: str = request.state.role
    entries = await list_permissions(db, collection_id, current_user, role)
    return DataResponse(data=entries)


@router.post("/{collection_id}/permissions", status_code=201)
async def permission_grant(
    collection_id: str,
    body: PermissionGrant,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PermissionEntry]:
    """Grant a user explicit read access to a collection. EditorInChief+ only.

    Idempotent: re-granting an existing permission returns the existing entry
    with HTTP 201 (no duplicate row is created).
    """
    role: str = request.state.role
    entry = await grant_permission(db, collection_id, body, current_user, role)
    return DataResponse(data=entry)


@router.delete("/{collection_id}/permissions/{user_id}", status_code=204)
async def permission_revoke(
    collection_id: str,
    user_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Revoke a user's explicit read access to a collection. EditorInChief+ only."""
    role: str = request.state.role
    await revoke_permission(db, collection_id, user_id, current_user, role)


# ── Collection-wide validation ────────────────────────────────────────────────
# NOTE: /validate-all/latest and /validate-all/{run_id} must be declared
# before any route that could shadow them.

@router.post("/{collection_id}/validate-all")
async def collection_validate_all_start(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionValidationRunResponse]:
    """Start an asynchronous full-collection validation run [EiC+].

    Validates every document against the schema attached to the collection.
    Returns immediately with the run record; poll the status endpoint to
    track progress.
    """
    role: str = request.state.role
    data = await start_validation_run(db, collection_id, current_user, role)
    return DataResponse(data=data)


@router.get("/{collection_id}/validate-all/latest")
async def collection_validate_all_latest(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionValidationRunResponse | None]:
    """Return the most recent validation run for the collection [EiC+]."""
    role: str = request.state.role
    data = await get_latest_validation_run(db, collection_id, current_user, role)
    return DataResponse(data=data)


@router.get("/{collection_id}/validate-all/{run_id}")
async def collection_validate_all_run(
    collection_id: str,
    run_id: int,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionValidationRunResponse]:
    """Return a specific validation run by ID [EiC+]."""
    role: str = request.state.role
    data = await get_validation_run(db, collection_id, run_id, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/validate-all/{run_id}/cancel")
async def collection_validate_all_cancel(
    collection_id: str,
    run_id: int,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionValidationRunResponse]:
    """Cancel a pending or running validation run [EiC+].

    Sets the run status to 'cancelled' immediately.  The background task
    checks for this status cooperatively and stops after the current document.
    """
    role: str = request.state.role
    data = await cancel_validation_run(db, collection_id, run_id, current_user, role)
    return DataResponse(data=data)


# ── Document validation ───────────────────────────────────────────────────────

@router.post("/{collection_id}/documents/{filename}/validate")
async def document_validate(
    collection_id: str,
    filename: str,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[ValidationResult]:
    """Validate a document against the collection's TEI schema.

    Requires the collection to have a schema with a validation file attached.
    Returns a ValidationResult with a list of errors (empty list = valid).
    Validation failure does not prevent saving — it is informational.
    """
    role: str = request.state.role
    result = await validate_document(db, existdb, collection_id, filename, current_user, role)
    return DataResponse(data=result)
