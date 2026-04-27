"""Rename ``ai_prompts.target_context`` to ``ai_prompts.scope``.

Promotes the dormant ``target_context`` field to a structured
``scope`` enum that the platform actually uses to wire prompts into
UI surfaces (the TEI editor toolbar, the XSLT editor toolbar, the
Bibliobuilder workflow). The values map 1:1 to call sites:

  • ``editor.selection``  — TEI editor button, input is the active
    selection (``filename``, ``collection_slug``, ``selection``).
  • ``editor.document``   — same surface, ``selection`` filled with
    the whole document (e.g. teiHeader scaffold).
  • ``editor.validation`` — TEI editor / Collection detail panel
    after a schema validation pass; output is plain text.
  • ``editor.discuss``    — TEI editor multi-turn chat.
  • ``xslt.debug``        — Website XSLT editor, fed the stylesheet
    plus an optional error message.
  • ``xslt.discuss``      — Website XSLT editor multi-turn chat.
  • ``bibliobuilder``     — surfaced inside the Bibliobuilder
    workflow as a "modalità" picker (multiple prompts allowed,
    one chosen per run).
  • ``NULL``              — orphan: visible only in Settings → AI;
    no UI surface auto-cables it.

The native prompts get back-filled to their canonical scope in the
data migration. Custom prompts that previously sat in the
deprecated buckets (``editor`` / ``validation`` / ``xslt``) are
mapped to the closest specific value:

  ``editor``     → ``editor.selection``
  ``validation`` → ``editor.validation``
  ``xslt``       → ``xslt.discuss``
  anything else  → ``NULL`` (admin can re-pick from the dropdown)

Revision ID: 0068
Revises: 0067
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


# Slug → canonical scope for the native prompts seeded by the platform.
_NATIVE_SCOPES = {
    "validate_errors_explain":  "editor.validation",
    "document_edit_suggest":    "editor.selection",
    "document_discuss":         "editor.discuss",
    "xslt_debug":               "xslt.debug",
    "xslt_discuss":             "xslt.discuss",
    "tei_bibl_inline":          "editor.selection",
    "tei_extract_entities":     "editor.selection",
    "tei_header_scaffold":      "editor.document",
    "bibliobuilder":            "bibliobuilder",
}


def upgrade() -> None:
    # Rename the column. Postgres handles the in-place rename; the new
    # name keeps the existing data, so we get a free audit of the
    # legacy values.
    op.alter_column(
        "ai_prompts",
        "target_context",
        new_column_name="scope",
        existing_type=sa.String(64),
        existing_nullable=True,
    )

    # Back-fill the natives to their canonical scope, then translate
    # the legacy bucket names for any custom row that happened to use
    # them.
    bind = op.get_bind()
    for slug, scope in _NATIVE_SCOPES.items():
        bind.execute(
            sa.text("UPDATE ai_prompts SET scope = :scope WHERE slug = :slug"),
            {"scope": scope, "slug": slug},
        )

    # Legacy custom-prompt buckets → closest specific scope.
    bind.execute(sa.text(
        "UPDATE ai_prompts SET scope = 'editor.selection' "
        "WHERE scope = 'editor'"
    ))
    bind.execute(sa.text(
        "UPDATE ai_prompts SET scope = 'editor.validation' "
        "WHERE scope = 'validation'"
    ))
    bind.execute(sa.text(
        "UPDATE ai_prompts SET scope = 'xslt.discuss' "
        "WHERE scope = 'xslt'"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    # Best-effort reverse mapping of the new scopes to the old buckets.
    bind.execute(sa.text(
        "UPDATE ai_prompts SET scope = 'editor' "
        "WHERE scope IN ('editor.selection', 'editor.document', 'editor.discuss')"
    ))
    bind.execute(sa.text(
        "UPDATE ai_prompts SET scope = 'validation' "
        "WHERE scope = 'editor.validation'"
    ))
    bind.execute(sa.text(
        "UPDATE ai_prompts SET scope = 'xslt' "
        "WHERE scope IN ('xslt.debug', 'xslt.discuss')"
    ))
    bind.execute(sa.text(
        "UPDATE ai_prompts SET scope = NULL WHERE scope = 'bibliobuilder'"
    ))

    op.alter_column(
        "ai_prompts",
        "scope",
        new_column_name="target_context",
        existing_type=sa.String(64),
        existing_nullable=True,
    )
