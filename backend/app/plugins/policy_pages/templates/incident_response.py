"""``incident_response`` — security incident response plan.

Categories: ``cts:R16`` (Security). Platform contributes the
existing security-review trail + Dependabot status; operator
declares contacts, escalation ladder, and disclosure timeline.
"""

import os
from pathlib import Path

from app.plugins.policy_pages.platform import plugin_active
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


def _security_review_files() -> list[str]:
    """Return the names of every ``Security_review_YYYY-MM-DD.md``
    file shipped under ``docs/`` in the running deployment.

    Best-effort — operates on the file system that the backend
    container can see; if the docs/ directory is not mounted (e.g.
    a slim production image), returns an empty list and the
    public render says "(none on file)".
    """
    candidates: list[Path] = []
    for env_root in ("DOCS_DIR", "REPO_ROOT"):
        v = os.environ.get(env_root)
        if v:
            candidates.append(Path(v))
    candidates.append(Path("/repo/docs"))
    candidates.append(Path("/app/../docs"))
    for c in candidates:
        if c.is_dir():
            return sorted(
                p.name for p in c.glob("Security_review_*.md")
            )
    return []


def _dependabot_present() -> str:
    return (
        "Yes — `.github/dependabot.yml` ships in the repository"
        if Path("/repo/.github/dependabot.yml").is_file()
        or Path("/app/../.github/dependabot.yml").is_file()
        else "Not in this deployment image"
    )


TEMPLATE = PolicyTemplate(
    slug="incident_response",
    title_key="policy.incident_response.title",
    categories=("cts:R16",),
    fields=(
        Field("security_review_files", "platform", source=_security_review_files,
              label_key="policy.incident_response.security_review_files"),
        Field("dependabot", "platform", source=_dependabot_present,
              label_key="policy.incident_response.dependabot"),
        Field("incident_contacts", "textarea", required=True, localized=True,
              label_key="policy.incident_response.incident_contacts",
              hint_key="policy.incident_response.incident_contacts_hint"),
        Field("escalation_ladder", "textarea", required=True, localized=True,
              label_key="policy.incident_response.escalation_ladder"),
        Field("disclosure_timeline_days", "integer", min=1, max=120,
              label_key="policy.incident_response.disclosure_timeline_days"),
        Field("post_mortem_policy", "textarea", localized=True,
              label_key="policy.incident_response.post_mortem_policy"),
    ),
    public_template="_default.md.j2",
)
