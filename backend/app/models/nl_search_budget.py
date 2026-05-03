"""ORM model for ``nl_search_budget_day`` — per-day spend / volume.

Phase NLS-A. One row per UTC day; the orchestrator increments
``eur_spent`` (estimated cost) and ``queries`` after each successful
LLM call. The endpoint short-circuits to 503 when ``eur_spent`` ≥
``nl_search_daily_budget_eur`` system_setting.

Ollama runs always add ``0`` to ``eur_spent`` — local provider, no
$ cost — but ``queries`` is still incremented so an operator can
see volume regardless of provider.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class NlSearchBudgetDay(Base):
    __tablename__ = "nl_search_budget_day"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    eur_spent: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=4), nullable=False, default=Decimal("0")
    )
    queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
