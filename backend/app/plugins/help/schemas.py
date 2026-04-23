"""Help plugin — Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HelpTreeNode(BaseModel):
    """One node of the navigation tree — either a section or a page."""

    model_config = ConfigDict(extra="forbid")

    # URL-like path relative to help_docs_root, without a leading slash
    # and without the .md extension. Empty string for the root page.
    path: str
    # Displayed label — first `# Heading` of a .md file, or the tidied
    # directory name for sections.
    title: str
    # True when this node is a directory; children is then populated.
    is_section: bool
    children: list["HelpTreeNode"] = []


HelpTreeNode.model_rebuild()


class HelpPage(BaseModel):
    """Rendered page payload returned to the frontend."""

    model_config = ConfigDict(extra="forbid")

    path: str
    title: str
    # Sanitised HTML ready to inject with `v-html`.
    html: str
    # Breadcrumb of (path, title) pairs from the root to this page,
    # inclusive of this page itself.
    breadcrumb: list[tuple[str, str]]


class HelpSearchHit(BaseModel):
    """One search result row."""

    model_config = ConfigDict(extra="forbid")

    path: str
    title: str
    # HTML snippet with <mark> wrapping the matched term(s).
    snippet: str
