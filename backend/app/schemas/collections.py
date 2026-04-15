import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.models.collection import CollectionStatus

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CollectionCreate(BaseModel):
    slug: str
    title: str
    description: str | None = None
    is_public: bool = False

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must contain only lowercase letters, digits and hyphens "
                "(e.g. 'dante-alighieri')"
            )
        if len(v) > 128:
            raise ValueError("slug must be 128 characters or fewer")
        return v

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title cannot be empty")
        return v


class RespStmtItem(BaseModel):
    resp: str
    name: str


class CollectionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_public: bool | None = None
    # schema_id / license_id: present in payload (even as null) means "set/clear";
    # absent from payload means "leave unchanged". Use model_fields_set to distinguish.
    schema_id: uuid.UUID | None = None
    # Publication metadata (TEI publicationStmt fields)
    publisher: str | None = None
    pub_place: str | None = None
    pub_year: int | None = None
    license_id: uuid.UUID | None = None
    # TEI respStmt — array of responsibility statements; None means "leave unchanged"
    resp_stmts: list[RespStmtItem] | None = None
    # Single author shared by all documents; None means "leave unchanged"
    author: str | None = None
    # Primary source for all documents; None means "leave unchanged"
    listbibl_bibl_main: str | None = None
    # Manuscript identifier; None means "leave unchanged"
    msidentifier_idno: str | None = None
    # Physical form of the source; None means "leave unchanged"
    objectdesc_form: Literal[
        "codex", "leaf", "roll", "tablet", "sheet", "fascicle", "fragment", "other"
    ] | None = None
    # Persistent identifier URL (DOI, Handle, URN, …); None means "leave unchanged"
    identifier_url: str | None = None
    # Body template for new documents; present in payload means "set/clear"
    body_template_id: uuid.UUID | None = None
    # Per-collection EVT viewer opt-in
    evt_enabled: bool | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("title cannot be empty")
        return v

    @field_validator("pub_year")
    @classmethod
    def pub_year_range(cls, v: int | None) -> int | None:
        if v is not None and not (1000 <= v <= 9999):
            raise ValueError("pub_year must be a 4-digit year (1000–9999)")
        return v


class CollectionResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    status: CollectionStatus
    is_public: bool
    owner_id: uuid.UUID | None
    editor_id: uuid.UUID | None
    assigned_at: datetime | None
    submitted_at: datetime | None
    published_at: datetime | None
    schema_id: uuid.UUID | None
    # Publication metadata
    publisher: str | None
    pub_place: str | None
    pub_year: int | None
    license_id: uuid.UUID | None
    # TEI respStmt
    resp_stmts: list[RespStmtItem] | None
    author: str | None
    listbibl_bibl_main: str | None
    msidentifier_idno: str | None
    objectdesc_form: str | None
    identifier_url: str | None
    body_template_id: uuid.UUID | None
    doc_count: int
    evt_enabled: bool
    created_at: datetime
    updated_at: datetime
    # Populated only on public collection listings when a published website
    # with show_in_public_home=True is linked to this collection.
    website_link: str | None = None
    # True when at least one saved bibliography version is marked is_public.
    has_public_bibliography: bool = False

    model_config = {"from_attributes": True}


class AssignAction(BaseModel):
    user_id: uuid.UUID
    note: str | None = None


class WorkflowAction(BaseModel):
    note: str | None = None


class RejectAction(BaseModel):
    note: str


class DocumentInfo(BaseModel):
    filename: str


class DocumentValidateRequest(BaseModel):
    xml_content: str | None = None  # when provided, validate this content instead of the saved file


class PermissionEntry(BaseModel):
    collection_id: uuid.UUID
    user_id: uuid.UUID
    granted_by_id: uuid.UUID | None
    granted_at: datetime

    model_config = {"from_attributes": True}


class PermissionGrant(BaseModel):
    user_id: uuid.UUID


class SearchHit(BaseModel):
    filename: str
    snippet: str


class DocumentMeta(BaseModel):
    root_element: str
    namespace: str
    size: int
    child_count: int


class ZipUploadError(BaseModel):
    filename: str
    error: str


class ZipUploadResult(BaseModel):
    uploaded: int
    skipped: list[str]
    errors: list[ZipUploadError]


class PublicDocHit(BaseModel):
    filename: str
    snippet: str


class PublicCollectionSearchResult(BaseModel):
    """One collection matched by a public full-text search, with optional doc snippets."""
    collection: CollectionResponse
    doc_hits: list[PublicDocHit]
