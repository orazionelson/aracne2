"""Pydantic schemas for the Webhook Dispatcher plugin."""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

# All event names that can be routed to webhooks.
SUPPORTED_EVENTS: list[str] = [
    "collection.submitted",
    "collection.published",
    "collection.unpublished",
    "document.uploaded",
    "document.deleted",
    "user.created",
]


class WebhookEndpointCreate(BaseModel):
    label: str
    url: str
    events: list[str]
    secret: str | None = None
    active: bool = True

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("label cannot be empty")
        return v.strip()

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def events_must_be_valid(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one event must be selected")
        invalid = set(v) - set(SUPPORTED_EVENTS)
        if invalid:
            raise ValueError(f"Unknown events: {', '.join(sorted(invalid))}")
        return list(dict.fromkeys(v))  # deduplicate, preserve order


class WebhookEndpointUpdate(BaseModel):
    label: str | None = None
    url: str | None = None
    events: list[str] | None = None
    secret: str | None = None
    active: bool | None = None

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("events")
    @classmethod
    def events_must_be_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("At least one event must be selected")
        invalid = set(v) - set(SUPPORTED_EVENTS)
        if invalid:
            raise ValueError(f"Unknown events: {', '.join(sorted(invalid))}")
        return list(dict.fromkeys(v))


class WebhookEndpointResponse(BaseModel):
    id: uuid.UUID
    label: str
    url: str
    events: list[str]
    secret_set: bool  # never expose the raw secret
    active: bool
    last_triggered_at: datetime | None
    last_status_code: int | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
