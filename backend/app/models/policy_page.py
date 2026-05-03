"""ORM models for ``policy_pages`` + ``policy_page_versions``.

Phase PP-A of Milestone 3. See migration
[`0080_policy_pages.py`](../alembic/versions/0080_policy_pages.py)
for column rationale.

The two-table layout mirrors ``document_versions`` from M1 §7
intentionally so the codebase has one mental model for "thing with
an append-only edit history". Save = new ``policy_page_versions``
row; Publish = update ``policy_pages.published_version_id`` to
point at the desired version.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base
from app.db.types import JsonbType


def _now() -> datetime:
    return datetime.now(UTC)


class PolicyPage(Base):
    """One concrete instance of a built-in policy template.

    The ``template_slug`` (e.g. ``"storage_policy"``) names the
    PolicyTemplate the row was created from. ``slug`` is the URL
    slug (kebab form, e.g. ``"storage-policy"``) — at most one row
    per (template, deployment).

    ``published_version_id`` points at the specific
    ``policy_page_versions`` row currently exposed at
    ``/policies/<slug>``. ``NULL`` means the policy has only
    drafts; the public 404s, only Editor+ readers see the form.
    """

    __tablename__ = "policy_pages"
    __table_args__ = (
        UniqueConstraint(
            "template_slug", name="uq_policy_pages_template_slug"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # FK to the version row currently published. The use_alter on the FK
    # name in the migration is required because policy_page_versions also
    # carries a FK back to policy_pages — circular references need the
    # explicit constraint name on at least one side.
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "policy_page_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_policy_pages_published_version_id",
        ),
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    versions: Mapped[list["PolicyPageVersion"]] = relationship(
        "PolicyPageVersion",
        back_populates="page",
        cascade="all, delete-orphan",
        foreign_keys="PolicyPageVersion.policy_page_id",
    )


class PolicyPageVersion(Base):
    """One Save snapshot of a ``policy_pages`` row.

    ``version_number`` is monotonic per ``policy_page_id`` (computed
    in the service layer as ``MAX(version_number) + 1`` inside the
    same transaction as the row write).

    ``content_jsonb`` carries the Field values keyed by Field name.
    Multi-locale fields store a per-locale dict (e.g. ``{"it":
    "...", "en": "..."}``); single-locale fields store the value
    directly.
    """

    __tablename__ = "policy_page_versions"
    __table_args__ = (
        UniqueConstraint(
            "policy_page_id",
            "version_number",
            name="uq_policy_page_versions_page_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    policy_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policy_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_jsonb: Mapped[dict[str, object]] = mapped_column(
        JsonbType, nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    saved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    page: Mapped["PolicyPage"] = relationship(
        "PolicyPage",
        back_populates="versions",
        foreign_keys=[policy_page_id],
    )
