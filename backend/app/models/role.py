import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base
from app.db.types import BigIntType, SmallIntType


def _now() -> datetime:
    return datetime.now(UTC)


class RoleName(str, enum.Enum):
    Admin = "Admin"
    EditorInChief = "EditorInChief"
    Designer = "Designer"
    Editor = "Editor"
    User = "User"
    # Capability roles — orthogonal to the hierarchy. PolicyManager
    # (M3 §27) is the first; future singleton or multi-holder
    # capability roles land as additional values here.
    PolicyManager = "PolicyManager"


class RoleKind(str, enum.Enum):
    """Whether a role participates in the hierarchy or is a capability.

    ``hierarchical`` rows feed ``require_role(min_role=…)`` via the
    ``ROLE_LEVEL`` map; ``capability`` rows feed
    ``require_capability(name)`` via a direct user_role membership
    check. The two ladders are independent — a User can hold both
    ``User`` (hierarchical) and ``PolicyManager`` (capability)
    simultaneously.
    """

    hierarchical = "hierarchical"
    capability = "capability"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallIntType, primary_key=True, autoincrement=True)
    name: Mapped[RoleName] = mapped_column(
        SAEnum(RoleName, name="role_name", create_type=False),
        nullable=False,
        unique=True,
    )
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RoleKind.hierarchical.value
    )
    singleton: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user_roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="role")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        # UNIQUE NULLS NOT DISTINCT (user_id, role_id, revoked_at)
        # Enforced in migration; declared here for documentation purposes only.
        UniqueConstraint("user_id", "role_id", "revoked_at", name="uq_user_active_role"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[user_id], back_populates="user_roles"
    )
