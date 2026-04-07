import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class SchemaFormat(str, enum.Enum):
    rng = "rng"
    dtd = "dtd"
    xsd = "xsd"


class TeiSchema(Base):
    """Represents a TEI schema that can be attached to a collection.

    Each record may have two independent files stored on the filesystem:
    - A validation schema (RNG / DTD / XSD) used to validate XML documents.
    - A CM5 autocomplete schema (custom XML format) used by the CodeMirror editor.

    Files are stored at ``settings.schemas_dir / str(id) / "validation.<ext>"``
    and ``settings.schemas_dir / str(id) / "cm5.xml"`` respectively.
    The presence of a file is tracked via the corresponding ``*_filename`` column
    (non-null = file exists on disk).
    """

    __tablename__ = "tei_schemas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # Validation schema (RNG / DTD / XSD) — optional
    validation_filename: Mapped[str | None] = mapped_column(String(512), default=None)
    validation_format: Mapped[SchemaFormat | None] = mapped_column(
        SAEnum(SchemaFormat, name="schema_format", create_type=False),
        default=None,
    )

    # CM5 autocomplete schema — optional
    cm5_filename: Mapped[str | None] = mapped_column(String(512), default=None)

    # Audit
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
