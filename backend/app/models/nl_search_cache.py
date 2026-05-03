"""ORM model for ``nl_search_cache`` — identical-query response cache.

Phase NLS-A of the natural-language search plugin. See migration
[`0076_nl_search_cache.py`](../alembic/versions/0076_nl_search_cache.py)
for column rationale and TTL semantics.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class NlSearchCache(Base):
    __tablename__ = "nl_search_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
