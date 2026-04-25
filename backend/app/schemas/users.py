import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.orcid import is_valid_orcid, normalise_orcid


class RoleInfo(BaseModel):
    """Single active role entry as returned in user detail."""

    role_name: str
    assigned_at: datetime

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Safe user representation — no password_hash, ip_address or user_agent."""

    id: uuid.UUID
    username: str
    email: str
    display_name: str | None
    preferred_lang: str
    is_active: bool
    is_verified: bool
    role: str            # highest active role (same derivation as JWT)
    roles: list[RoleInfo]  # all active role assignments
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    deleted_at: datetime | None
    orcid: str | None = None
    avatar_url: str | None = None
    bio: str | None = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    """Payload for Admin creating a new user."""

    username: str
    email: EmailStr
    password: str
    display_name: str | None = None
    preferred_lang: str = "it"
    role: str = "User"

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def username_no_spaces(cls, v: str) -> str:
        if not v.strip() or " " in v:
            raise ValueError("Username must not contain spaces")
        return v.strip()

    @field_validator("preferred_lang")
    @classmethod
    def lang_valid(cls, v: str) -> str:
        if v not in ("it", "en"):
            raise ValueError("preferred_lang must be 'it' or 'en'")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        valid = {"Admin", "EditorInChief", "Designer", "Editor", "User"}
        if v not in valid:
            raise ValueError(f"role must be one of: {', '.join(sorted(valid))}")
        return v


class UserUpdate(BaseModel):
    """Payload for Admin patching a user. All fields optional."""

    email: EmailStr | None = None
    display_name: str | None = None
    preferred_lang: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    orcid: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("preferred_lang")
    @classmethod
    def lang_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("it", "en"):
            raise ValueError("preferred_lang must be 'it' or 'en'")
        return v

    @field_validator("orcid")
    @classmethod
    def orcid_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = normalise_orcid(v)
        if cleaned == "":
            return ""
        if not is_valid_orcid(cleaned):
            raise ValueError(
                "orcid must be in the form XXXX-XXXX-XXXX-XXXX with a valid checksum"
            )
        return cleaned


class RoleAssignRequest(BaseModel):
    """Payload for assigning a role to a user."""

    role_name: str

    @field_validator("role_name")
    @classmethod
    def role_valid(cls, v: str) -> str:
        valid = {"Admin", "EditorInChief", "Designer", "Editor", "User"}
        if v not in valid:
            raise ValueError(f"role_name must be one of: {', '.join(sorted(valid))}")
        return v


class UserExport(BaseModel):
    """Personal data export for GDPR art. 20."""

    id: str
    username: str
    email: str
    display_name: str | None
    preferred_lang: str
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None
    active_roles: list[str]
    active_sessions_count: int  # count only — no ip/ua details
