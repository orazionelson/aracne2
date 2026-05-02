import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base
from app.db.types import JsonbType


def _now() -> datetime:
    return datetime.now(UTC)


class CollectionStatus(str, enum.Enum):
    draft = "draft"
    assigned = "assigned"
    review = "review"
    published = "published"


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # Workflow
    status: Mapped[CollectionStatus] = mapped_column(
        SAEnum(CollectionStatus, name="collection_status", create_type=False),
        nullable=False,
        default=CollectionStatus.draft,
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="FALSE"
    )

    # Actors — SET NULL so that deleting a user does not cascade-delete collections
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    editor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    # Transition timestamps — set by services, never by the ORM default
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Fingerprint of the working tree captured at the last successful publish.
    # Lets ``publish_collection`` short-circuit re-publishes on unchanged
    # content so deposit hooks (Zenodo / Internet Archive / Dataverse /
    # webhooks) do not duplicate side effects.
    last_published_tree_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    # TEI schema attached to this collection (nullable — no schema = no validation/autocomplete)
    schema_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tei_schemas.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    # Publication metadata (maps to TEI publicationStmt fields)
    publisher: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    pub_place: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    pub_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, default=None)
    # availability: FK to the license selected for this collection
    license_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("licenses.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    # TEI respStmt — array of {resp, name} objects stored as JSONB
    resp_stmts: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JsonbType(), nullable=True, default=None
    )
    # Single author shared by all documents in the collection (optional)
    author: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    # Primary source for all documents — maps to <listBibl><bibl type="main_source">
    listbibl_bibl_main: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None
    )
    # Manuscript identifier — maps to <msDesc><msIdentifier><idno>
    msidentifier_idno: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None
    )
    # Physical form of the source — maps to <msDesc><physDesc><objectDesc form="...">
    objectdesc_form: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    # Persistent identifier URL (DOI, Handle, URN, …)
    identifier_url: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
    # Denormalized count of XML documents stored in eXist-db for this collection.
    # Updated after every document upload, delete, or ZIP batch operation.
    doc_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Per-collection EVT viewer opt-in. The global evt_enabled setting must also
    # be true for the "View in EVT" button to appear.
    evt_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="FALSE"
    )

    # Per-collection override for the Zenodo deposit plugin's resource_type.
    # When NULL the plugin falls back to the global `zenodo_resource_type`
    # system_setting. Values are InvenioRDM vocabulary ids
    # (e.g. "publication-book", "image-photo", "dataset").
    zenodo_resource_type: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=None
    )
    # When true, the Zenodo deposit plugin bundles every TEI document into a
    # single ZIP archive ({slug}.zip) instead of uploading individual files.
    # Useful for large collections or when the editor wants the record's
    # "files" tab to stay a single downloadable artefact.
    zenodo_upload_as_zip: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="FALSE"
    )

    # Soft target date for publication, set by the EiC to flag work that
    # should be out by a certain day. The workflow panel renders a
    # countdown badge based on this value and nudges (amber) when it
    # goes overdue. Purely informational — no backend enforcement.
    target_publish_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )

    # Body template applied to new documents created in this collection
    body_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("body_templates.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    # Relationships (lazy by default — loaded only when accessed)
    owner: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[owner_id]
    )
    editor: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[editor_id]
    )
