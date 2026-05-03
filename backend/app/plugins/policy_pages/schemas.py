"""Pydantic schemas for the policy_pages REST surface — Phase PP-F."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field as PyField


class PolicyTemplateDescriptor(BaseModel):
    """The template's static description, served to the admin form
    so the SPA can render the right field types per template."""

    slug: str
    url_slug: str
    title_key: str
    categories: list[str]
    fields: list[dict[str, Any]]


class PolicyPageListItem(BaseModel):
    """One entry in the admin's policy-list view."""

    template_slug: str
    url_slug: str
    title_key: str
    categories: list[str]
    is_published: bool
    latest_version_number: int | None = None
    latest_saved_at: str | None = None


class PolicyPageDetail(BaseModel):
    """The admin form's hydration payload."""

    template: PolicyTemplateDescriptor
    is_published: bool
    published_version_number: int | None = None
    latest_version_number: int | None = None
    latest_content: dict[str, Any] = PyField(default_factory=dict)
    platform_values: dict[str, Any] = PyField(default_factory=dict)


class PolicyPageVersionView(BaseModel):
    """One row of the per-page version history."""

    id: UUID
    version_number: int
    content_sha256: str
    message: str | None = None
    saved_at: datetime
    saved_by_username: str | None = None
    is_published: bool


class SaveDraftRequest(BaseModel):
    """Body for ``POST /policies/{slug}/save``."""

    content: dict[str, Any]
    message: str | None = None


class PublishRequest(BaseModel):
    """Body for ``POST /policies/{slug}/publish``.

    ``version_number`` is optional — when omitted, the most-recent
    saved version is promoted. Allows an admin to roll back to a
    previous draft by publishing it explicitly.
    """

    version_number: int | None = None


class PolicyRenderResponse(BaseModel):
    """Body of the public ``GET /policies/<slug>`` endpoint."""

    title: str
    locale: str
    html: str
    version_number: int
    saved_at: datetime
    saved_by: str | None = None
