"""Pydantic schemas for the admin audit-log view (FUTURE_IDEAS §20)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    """One audit-log row as returned in the paginated list.

    The ``payload`` JSONB is omitted from the list to keep responses
    lean; ``GET /audit-log/{id}`` returns the full row including
    ``payload``.
    """

    id: int
    occurred_at: datetime
    action: str
    actor_id: UUID | None
    actor_username: str | None
    target_type: str | None
    target_id: str | None
    target_label: str | None

    model_config = {"from_attributes": True}


class AuditLogDetail(AuditLogEntry):
    """One audit-log row including its JSONB payload + user_agent.

    ``ip_address`` is not exposed even to admins — the production
    logger middleware hashes it before it ever reaches the table,
    and surfacing the hash adds nothing useful in the UI while
    paying a privacy cost.
    """

    payload: dict[str, object] | None = None
    user_agent: str | None = None
