"""
TEI schema management router.

All write endpoints require EditorInChief or above [EiC+].
The cm5-file endpoint is available to any authenticated user [auth]
because the editor needs to load it when opening a document.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user, require_role
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.tei_schemas import (
    ImportUrl,
    TeiSchemaCreate,
    TeiSchemaResponse,
)
from app.services import schemas as svc

router = APIRouter(prefix="/schemas", tags=["schemas"])

_auth = Depends(get_current_user)
_eic = Depends(require_role(min_role="EditorInChief"))


@router.get("")
async def schema_list(
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[TeiSchemaResponse]]:
    """List all registered TEI schemas. Any authenticated user."""
    data = await svc.list_schemas(db)
    return DataResponse(data=data)


@router.post("", status_code=201)
async def schema_create(
    body: TeiSchemaCreate,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TeiSchemaResponse]:
    """Create a new (empty) schema entry. [EiC+]"""
    data = await svc.create_schema(db, body, current_user)
    await db.commit()
    return DataResponse(data=data)


@router.delete("/{schema_id}", status_code=204)
async def schema_delete(
    schema_id: uuid.UUID,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Delete a schema and its files. [EiC+]"""
    await svc.delete_schema(db, schema_id)
    await db.commit()


# ── Validation file endpoints ──────────────────────────────────────────────────

@router.post("/{schema_id}/upload-validation")
async def schema_upload_validation(
    schema_id: uuid.UUID,
    file: UploadFile,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TeiSchemaResponse]:
    """Upload a validation schema file (RNG / DTD / XSD). [EiC+]"""
    content = await file.read()
    data = await svc.upload_validation(db, schema_id, file.filename or "", content)
    await db.commit()
    return DataResponse(data=data)


@router.post("/{schema_id}/import-validation")
async def schema_import_validation(
    schema_id: uuid.UUID,
    body: ImportUrl,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TeiSchemaResponse]:
    """Import a validation schema from a public URL (SSRF-guarded). [EiC+]"""
    data = await svc.import_validation(db, schema_id, body.url)
    await db.commit()
    return DataResponse(data=data)


# ── CM5 file endpoints ─────────────────────────────────────────────────────────

@router.post("/{schema_id}/upload-cm5")
async def schema_upload_cm5(
    schema_id: uuid.UUID,
    file: UploadFile,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TeiSchemaResponse]:
    """Upload the CM5 autocomplete schema file. [EiC+]"""
    content = await file.read()
    data = await svc.upload_cm5(db, schema_id, file.filename or "", content)
    await db.commit()
    return DataResponse(data=data)


@router.post("/{schema_id}/import-cm5")
async def schema_import_cm5(
    schema_id: uuid.UUID,
    body: ImportUrl,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TeiSchemaResponse]:
    """Import the CM5 schema from a public URL (SSRF-guarded). [EiC+]"""
    data = await svc.import_cm5(db, schema_id, body.url)
    await db.commit()
    return DataResponse(data=data)


@router.post("/{schema_id}/generate-cm5")
async def schema_generate_cm5(
    schema_id: uuid.UUID,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TeiSchemaResponse]:
    """Generate a CM5 autocomplete schema from the uploaded validation schema. [EiC+]

    Parses the stored RNG / XSD / DTD file, extracts element and attribute
    structure, and writes ``generated-cm5.xml``.  No request body needed.
    """
    data = await svc.generate_cm5(db, schema_id)
    await db.commit()
    return DataResponse(data=data)


@router.get("/{schema_id}/cm5-file")
async def schema_cm5_file(
    schema_id: uuid.UUID,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Serve the raw CM5 schema XML to the document editor. [auth]"""
    content = await svc.get_cm5_content(db, schema_id)
    return Response(content=content, media_type="application/xml")
