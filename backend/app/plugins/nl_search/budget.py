"""Daily-spend budget gate for the NL search plugin.

Phase NLS-C. Three responsibilities:

1. :func:`is_over_cap` — read today's row vs. the
   ``nl_search_daily_budget_eur`` setting; return True when spend is
   already at or above the cap. The endpoint short-circuits to 503
   ``BUDGET_EXCEEDED`` when this is True.
2. :func:`record_spend` — upsert today's row with one more query and
   ``+eur`` more spend.
3. :func:`estimate_eur` — convert a :class:`Usage` token pair into
   EUR using a per-model rate table. Ollama runs always estimate to
   ``0`` so the budget table tracks volume but not cost there.

The rate table is a small static dict — the operator's deployment is
billed at one vendor at a time, and per-model rates rarely change
faster than the project's release cadence. When a model is missing
from the table the function falls back to a conservative high
estimate so an unrecognised model can never bypass the budget.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nl_search_budget import NlSearchBudgetDay
from app.plugins.nl_search.providers.base import Usage
from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()


_DEFAULT_BUDGET_EUR = Decimal("2.00")

# Per-million-token EUR rate, indexed by ``provider:model``. The
# numbers are deliberate over-estimates so a missing entry never
# under-bills. Operator with tighter cost tracking edits the dict.
_RATE_TABLE_EUR_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    # provider:model         (input_per_mtok, output_per_mtok)
    "anthropic:claude-sonnet-4-6":   (Decimal("3.0"), Decimal("15.0")),
    "anthropic:claude-opus-4-7":     (Decimal("15.0"), Decimal("75.0")),
    "anthropic:claude-haiku-4-5":    (Decimal("0.80"), Decimal("4.00")),
}
_FALLBACK_RATE_EUR_PER_MTOK = (Decimal("10.0"), Decimal("50.0"))


def estimate_eur(*, provider: str, model: str, usage: Usage) -> Decimal:
    """Estimate the EUR cost of one round.

    Ollama: always 0.
    Cloud: ``(input_tokens × in_rate + output_tokens × out_rate) / 1e6``.
    """
    if provider.lower() == "ollama":
        return Decimal("0")
    key = f"{provider.lower()}:{model.lower()}"
    in_rate, out_rate = _RATE_TABLE_EUR_PER_MTOK.get(
        key, _FALLBACK_RATE_EUR_PER_MTOK
    )
    cost = (
        Decimal(usage.input_tokens) * in_rate
        + Decimal(usage.output_tokens) * out_rate
    ) / Decimal("1000000")
    return cost.quantize(Decimal("0.0001"))


async def _read_cap_eur(db: AsyncSession) -> Decimal:
    raw = (await get_decrypted_setting(db, "nl_search_daily_budget_eur")).strip()
    if not raw:
        return _DEFAULT_BUDGET_EUR
    try:
        return Decimal(raw)
    except Exception:
        return _DEFAULT_BUDGET_EUR


def _today() -> date:
    return datetime.now(UTC).date()


async def is_over_cap(db: AsyncSession) -> bool:
    """Return True when today's spend is already ≥ the cap."""
    cap = await _read_cap_eur(db)
    if cap <= Decimal("0"):
        return False  # cap of 0 disables the gate
    row = await db.get(NlSearchBudgetDay, _today())
    if row is None:
        return False
    return Decimal(row.eur_spent) >= cap


async def record_spend(db: AsyncSession, *, eur: Decimal) -> None:
    """Increment today's row by one query and ``+eur`` of spend."""
    day = _today()
    row = await db.get(NlSearchBudgetDay, day)
    if row is None:
        db.add(
            NlSearchBudgetDay(
                day=day,
                eur_spent=eur,
                queries=1,
            )
        )
    else:
        await db.execute(
            update(NlSearchBudgetDay)
            .where(NlSearchBudgetDay.day == day)
            .values(
                eur_spent=NlSearchBudgetDay.eur_spent + eur,
                queries=NlSearchBudgetDay.queries + 1,
            )
        )
    await db.flush()


__all__ = ["is_over_cap", "record_spend", "estimate_eur"]
