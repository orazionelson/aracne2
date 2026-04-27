import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AiPromptResponse(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    description: str | None
    template: str
    context_vars: list[str]
    target_context: str | None
    is_native: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AiPromptCreate(BaseModel):
    slug: str
    label: str
    description: str | None = None
    template: str
    context_vars: list[str] = []
    target_context: str | None = None

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("slug must contain only lowercase letters, digits and underscores")
        return v

    @field_validator("template")
    @classmethod
    def template_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("template cannot be empty")
        return v


class AiPromptUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    template: str | None = None
    context_vars: list[str] | None = None
    target_context: str | None = None


class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    # 500 KB per message — wide enough for a full bibliography dump
    # (Bibliobuilder regularly ships 100k+ chars in one user turn) but
    # still bounded against accidental DoS. The actual upper bound is
    # the LLM provider's context window, not this number.
    content: str = Field(..., max_length=500_000)


class AiCompleteRequest(BaseModel):
    prompt_slug: str
    context: dict[str, str] = Field(default_factory=dict, max_length=20)
    history: list[AiChatMessage] = Field(default=[], max_length=40)


class AiConfigResponse(BaseModel):
    provider: str
    model: str
    rate_limit: int
    privacy_warning: bool
