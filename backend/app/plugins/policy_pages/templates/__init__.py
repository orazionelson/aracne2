"""Built-in policy template catalogue.

Each template is a Python module under
``app.plugins.policy_pages.templates`` exporting a single
``TEMPLATE`` constant of type :class:`PolicyTemplate`. The
catalogue is registered eagerly at import time via
:func:`load_all` so the admin UI can list every available
template without duck-typing through directory entries at
request time.

The loader is intentionally simple: a hardcoded list of module
slugs maps to a static set of templates the platform ships with.
A future "user-supplied templates" feature would extend this with
a dynamic-discovery layer; for v1 the curated list keeps the
surface predictable.
"""

from __future__ import annotations

import importlib
from functools import lru_cache

from app.plugins.policy_pages.templates._base import PolicyTemplate

# Hardcoded order = the order admins see in the list view.
_TEMPLATE_SLUGS: tuple[str, ...] = (
    "mission",
    "privacy_dpia",
    "storage_policy",
    "continuity_plan",
    "preservation_plan",
    "appraisal_policy",
    "incident_response",
    "citation_guide",
    "editorial_board",
    "funding_staffing",
    "expert_directory",
    "cts_self_assessment",
)


@lru_cache(maxsize=1)
def load_all() -> dict[str, PolicyTemplate]:
    """Eagerly import every shipped template module and return the
    ``slug -> PolicyTemplate`` map.

    Cached per-process because templates are static; restart the
    backend after a code change to pick it up. The map is
    insertion-ordered (Python 3.7+) following ``_TEMPLATE_SLUGS``.
    """
    out: dict[str, PolicyTemplate] = {}
    for slug in _TEMPLATE_SLUGS:
        module = importlib.import_module(
            f"app.plugins.policy_pages.templates.{slug}"
        )
        template: PolicyTemplate = module.TEMPLATE  # type: ignore[attr-defined]
        if template.slug != slug:
            raise RuntimeError(
                f"Template module {slug!r} declares slug={template.slug!r}; "
                "they must match for the URL routing to be predictable."
            )
        out[slug] = template
    return out


def get_template(slug: str) -> PolicyTemplate:
    """Return the template for *slug*, raising KeyError when unknown."""
    return load_all()[slug]


__all__ = ["load_all", "get_template"]
