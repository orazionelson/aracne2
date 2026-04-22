"""Smoke tests for the native AI prompt library.

These tests do NOT call any real LLM provider. They verify:
- seed_ai_prompts inserts every native prompt with is_native=True
- each prompt's template can be rendered with its declared context_vars
  (the service layer's _fill_template uses ``template.format_map`` which
  raises KeyError on a missing variable — this catches drift between
  the template body and the declared context_vars).

Full end-to-end evaluation against a real provider is deferred — see
docs/FUTURE_IDEAS.md.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed import DEFAULT_AI_PROMPTS, seed_ai_prompts
from app.models.ai_prompt import AiPrompt
from app.plugins._native.ai.service import _fill_template


@pytest.mark.asyncio
async def test_seed_ai_prompts_inserts_all_native_entries(
    db_session: AsyncSession,
) -> None:
    await seed_ai_prompts(db_session)

    rows = list(await db_session.scalars(select(AiPrompt)))
    assert {r.slug for r in rows} == {p[0] for p in DEFAULT_AI_PROMPTS}
    # All seeded prompts are marked as native (cannot be deleted by users).
    assert all(r.is_native for r in rows)


@pytest.mark.asyncio
async def test_seed_ai_prompts_is_idempotent(db_session: AsyncSession) -> None:
    await seed_ai_prompts(db_session)
    first = {r.slug: (r.label, r.template) for r in await db_session.scalars(select(AiPrompt))}

    # Running seed again must not create duplicates nor change content when
    # the seed definition hasn't changed.
    await seed_ai_prompts(db_session)
    second = {r.slug: (r.label, r.template) for r in await db_session.scalars(select(AiPrompt))}

    assert first.keys() == second.keys()
    assert first == second


# Minimal context values used to render every native prompt. The dict is a
# superset of every prompt's context_vars; _fill_template ignores extras.
_SAMPLE_CONTEXT: dict[str, str] = {
    "filename": "test.xml",
    "collection_slug": "test-collection",
    "selection": "<p>example</p>",
    "schema": "tei_all",
    "errors": "Element 'foo' not declared.",
    "error_msg": "XSLT parse error at line 3.",
    "xslt_source": "<xsl:stylesheet/>",
}


@pytest.mark.parametrize("slug,label,description,template,context_vars,target_context", DEFAULT_AI_PROMPTS)
def test_prompt_template_renders_with_declared_context_vars(
    slug: str,
    label: str,
    description: str,
    template: str,
    context_vars: list[str],
    target_context: str | None,
) -> None:
    """Every {variable} in the template body must be covered by context_vars.

    _fill_template passes the dict via ``str.format_map``; missing keys raise
    KeyError that the service wraps into DomainValidationError. This test
    catches the drift at build time.
    """
    context = {k: _SAMPLE_CONTEXT.get(k, f"<{k}>") for k in context_vars}
    # Must not raise.
    rendered = _fill_template(template, context)
    # Sanity: rendered length > template length only if we filled variables;
    # equal when context_vars is empty.
    assert isinstance(rendered, str)
    assert len(rendered) >= 0


@pytest.mark.asyncio
async def test_new_tei_prompts_cover_editor_context(
    db_session: AsyncSession,
) -> None:
    """The three new TEI prompts are scoped to the editor context so the
    document editor's AI panel surfaces them."""
    await seed_ai_prompts(db_session)
    rows = {
        r.slug: r
        for r in await db_session.scalars(
            select(AiPrompt).where(
                AiPrompt.slug.in_(
                    ["tei_bibl_inline", "tei_extract_entities", "tei_header_scaffold"]
                )
            )
        )
    }
    assert set(rows) == {"tei_bibl_inline", "tei_extract_entities", "tei_header_scaffold"}
    for prompt in rows.values():
        assert prompt.target_context == "editor"
        assert set(prompt.context_vars) == {"filename", "collection_slug", "selection"}
