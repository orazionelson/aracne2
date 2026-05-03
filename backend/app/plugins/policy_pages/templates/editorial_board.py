"""``editorial_board`` — editorial board membership and governance.

Categories: ``core``. Pure operator declaration — multi-row form
for board members + free-text governance notes.
"""

from app.plugins.policy_pages.templates._base import Field, PolicyTemplate

TEMPLATE = PolicyTemplate(
    slug="editorial_board",
    title_key="policy.editorial_board.title",
    categories=("core",),
    fields=(
        Field("board_members", "rows", required=True,
              label_key="policy.editorial_board.board_members",
              hint_key="policy.editorial_board.board_members_hint",
              rows_fields=(
                  Field("name", "text", required=True,
                        label_key="policy.editorial_board.member_name"),
                  Field("role", "text", required=True, localized=True,
                        label_key="policy.editorial_board.member_role"),
                  Field("affiliation", "text", localized=True,
                        label_key="policy.editorial_board.member_affiliation"),
                  Field("orcid", "text",
                        label_key="policy.editorial_board.member_orcid"),
              )),
        Field("advisory_committee", "textarea", localized=True,
              label_key="policy.editorial_board.advisory_committee"),
        Field("governance_notes", "textarea", localized=True,
              label_key="policy.editorial_board.governance_notes"),
        Field("term_length_years", "integer", min=1, max=20,
              label_key="policy.editorial_board.term_length_years"),
    ),
    public_template="_default.md.j2",
)
