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
from app.middleware.rate_limiter import limiter
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.models.collection_bibliography import CollectionBibliography
from app.core.constants import ROLE_LEVEL
from app.middleware.acl import get_current_user, require_role
from app.models.collection import CollectionStatus
from app.models.user import User
from app.schemas.collections import (
    AssignAction,
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    DocumentInfo,
    DocumentMeta,
    DocumentValidateRequest,
    PermissionEntry,
    PermissionGrant,
    PublicCollectionSearchResult,
    RejectAction,
    SearchHit,
    WorkflowAction,
    WorkflowHistoryEntry,
    ZipUploadResult,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.collection_bibliography import (
    CollectionBibliographyResponse,
    CollectionBibliographySave,
    CollectionBibliographySetPublic,
)
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
    direct_publish_collection,
    download_document,
    get_collection,
    get_document_metadata,
    grant_permission,
    list_collections,
    list_documents,
    list_permissions,
    list_workflow_history,
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
@limiter.limit("60/minute")
async def collections_public(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
) -> PaginatedResponse[CollectionResponse]:
    """List published + is_public collections. No authentication required."""
    from sqlalchemy import func, or_, select
    from app.models.collection import Collection
    from app.models.website import Website

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

    # For each collection that has a published website with show_in_public_home=True,
    # compute the link URL: website_url → collection.identifier_url → /sites/{slug}/
    website_map: dict[uuid.UUID, Website] = {}
    public_bib_set: set[uuid.UUID] = set()
    if rows:
        col_ids = [r.id for r in rows]
        websites = list(await db.scalars(
            select(Website).where(
                Website.collection_id.in_(col_ids),
                Website.show_in_public_home.is_(True),
                Website.is_published.is_(True),
            )
        ))
        for w in websites:
            if w.collection_id and w.collection_id not in website_map:
                website_map[w.collection_id] = w

        # One-query batch check: which collections have a public bibliography?
        pub_bib_rows = await db.execute(
            select(CollectionBibliography.collection_id)
            .where(
                CollectionBibliography.collection_id.in_(col_ids),
                CollectionBibliography.is_public.is_(True),
            )
            .distinct()
        )
        public_bib_set = {row[0] for row in pub_bib_rows}

        # One-query batch: entity occurrence counts per collection.
        from app.plugins._native.named_entities.models import EntityOccurrence
        entity_count_rows = await db.execute(
            select(
                EntityOccurrence.collection_id,
                func.count().label("cnt"),
            )
            .where(EntityOccurrence.collection_id.in_(col_ids))
            .group_by(EntityOccurrence.collection_id)
        )
        entity_count_map: dict[uuid.UUID, int] = {row[0]: row[1] for row in entity_count_rows}

    def _resolve_link(website: Website, identifier_url: str | None) -> str:
        if website.website_url:
            return website.website_url
        if identifier_url:
            return identifier_url
        return f"/sites/{website.slug}/"

    items: list[CollectionResponse] = []
    for r in rows:
        cr = CollectionResponse.model_validate(r)
        if r.id in website_map:
            cr.website_link = _resolve_link(website_map[r.id], r.identifier_url)
        if r.id in public_bib_set:
            cr.has_public_bibliography = True
        cr.entity_count = entity_count_map.get(r.id, 0)
        items.append(cr)

    return PaginatedResponse(
        data=items,
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


@router.post("/{collection_id}/direct-publish")
async def collection_direct_publish(
    collection_id: str,
    body: WorkflowAction,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    """Publish a collection directly from any status (EditorInChief+).

    Bypasses the draft → assigned → review → published workflow.
    Useful for batch imports, manual curation, or emergency publishing.
    """
    role: str = request.state.role
    data = await direct_publish_collection(db, collection_id, body, current_user, role)
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


@router.get("/{collection_id}/history")
async def collection_workflow_history(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[WorkflowHistoryEntry]]:
    """Return the editorial workflow transitions for a collection.

    Backs the timeline + inline revision-note surface on the detail
    page. Restricted to EiC+ because the payload can include
    revision-request notes addressed to the assigned editor.
    """
    role: str = request.state.role
    entries = await list_workflow_history(db, collection_id, current_user, role)
    return DataResponse(data=entries)


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


@router.get("/{collection_id}/extract-bibl")
async def extract_bibl(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> Response:
    """Extract all <bibl> and <biblStruct> elements from the collection [EiC+].

    Returns a namespace-free <entries> XML document suitable for feeding to
    the bibliobuilder AI prompt.  Each entry carries @source (document filename)
    and @n (sequence number within that document).
    """
    role: str = request.state.role
    col = await get_collection(db, collection_id, current_user, role)
    col_path = existdb.col_path(col.slug)
    xml_bytes = await existdb.xquery(
        "collections/extract_bibl.xq",
        {"collection_path": col_path},
    )
    return Response(content=xml_bytes, media_type="application/xml")


@router.post("/{collection_id}/bibliographies", status_code=201)
async def bibliography_save(
    collection_id: str,
    body: CollectionBibliographySave,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionBibliographyResponse]:
    """Save a new versioned bibliography snapshot for the collection [EiC+].

    The version number is assigned automatically as MAX(version) + 1 for the
    collection, starting at 1 for the first saved version.
    """
    role: str = request.state.role
    col = await get_collection(db, collection_id, current_user, role)
    col_uuid = col.id

    next_version_row = await db.execute(
        select(func.coalesce(func.max(CollectionBibliography.version), 0) + 1).where(
            CollectionBibliography.collection_id == col_uuid
        )
    )
    next_version: int = next_version_row.scalar_one()

    entry = CollectionBibliography(
        collection_id=col_uuid,
        version=next_version,
        content=body.content,
        created_by_id=current_user.id,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return DataResponse(data=CollectionBibliographyResponse.model_validate(entry))


@router.get("/{collection_id}/bibliographies")
async def bibliography_list(
    collection_id: str,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[CollectionBibliographyResponse]]:
    """List all saved bibliography versions for the collection [EiC+], newest first."""
    role: str = request.state.role
    col = await get_collection(db, collection_id, current_user, role)

    rows = await db.execute(
        select(CollectionBibliography)
        .where(CollectionBibliography.collection_id == col.id)
        .order_by(CollectionBibliography.version.desc())
    )
    entries = rows.scalars().all()
    return DataResponse(
        data=[CollectionBibliographyResponse.model_validate(e) for e in entries]
    )


@router.delete("/{collection_id}/bibliographies/{version}", status_code=204)
async def bibliography_delete(
    collection_id: str,
    version: int,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Delete a specific bibliography version [EiC+]."""
    role: str = request.state.role
    col = await get_collection(db, collection_id, current_user, role)

    row = await db.scalar(
        select(CollectionBibliography).where(
            CollectionBibliography.collection_id == col.id,
            CollectionBibliography.version == version,
        )
    )
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Bibliography version not found")
    await db.delete(row)
    await db.flush()


@router.patch("/{collection_id}/bibliographies/{version}")
async def bibliography_set_public(
    collection_id: str,
    version: int,
    body: CollectionBibliographySetPublic,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionBibliographyResponse]:
    """Set or unset the public flag on a bibliography version [EiC+].

    When is_public=True, all other versions for this collection are
    automatically set to is_public=False (only one can be public at a time).
    """
    from fastapi import HTTPException
    from sqlalchemy import update as sa_update

    role: str = request.state.role
    col = await get_collection(db, collection_id, current_user, role)

    row = await db.scalar(
        select(CollectionBibliography).where(
            CollectionBibliography.collection_id == col.id,
            CollectionBibliography.version == version,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Bibliography version not found")

    if body.is_public:
        # Un-publish all other versions for this collection first.
        await db.execute(
            sa_update(CollectionBibliography)
            .where(
                CollectionBibliography.collection_id == col.id,
                CollectionBibliography.version != version,
            )
            .values(is_public=False)
        )

    row.is_public = body.is_public
    await db.flush()
    await db.refresh(row)
    return DataResponse(data=CollectionBibliographyResponse.model_validate(row))


@router.get("/{collection_id}/public-bibliography")
async def bibliography_public_get(
    collection_id: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionBibliographyResponse]:
    """Return the public bibliography for a collection. No authentication required.

    Only exposed for collections that are published and is_public=True.
    """
    from fastapi import HTTPException
    from app.models.collection import Collection

    # Resolve slug or UUID.
    try:
        cid = uuid.UUID(collection_id)
        col = await db.get(Collection, cid)
    except ValueError:
        col = await db.scalar(select(Collection).where(Collection.slug == collection_id))

    if col is None or not col.is_public or col.status != CollectionStatus.published:
        raise HTTPException(status_code=404, detail="Collection not found")

    row = await db.scalar(
        select(CollectionBibliography).where(
            CollectionBibliography.collection_id == col.id,
            CollectionBibliography.is_public.is_(True),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No public bibliography for this collection")
    return DataResponse(data=CollectionBibliographyResponse.model_validate(row))


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
    body: DocumentValidateRequest,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[ValidationResult]:
    """Validate a document against the collection's TEI schema.

    Requires the collection to have a schema with a validation file attached.
    Returns a ValidationResult with a list of errors (empty list = valid).
    Validation failure does not prevent saving — it is informational.

    When ``xml_content`` is provided in the request body the supplied XML is
    validated directly instead of fetching the saved file from eXist-db.  This
    allows the editor to validate unsaved content.
    """
    role: str = request.state.role
    result = await validate_document(
        db, existdb, collection_id, filename, current_user, role,
        xml_content=body.xml_content,
    )
    return DataResponse(data=result)
