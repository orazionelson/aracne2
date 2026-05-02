from pydantic import BaseModel, Field, field_validator

from app.core.orcid import is_valid_orcid, normalise_orcid


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105


class ImpersonationResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    impersonated_user: "UserMeResponse"


class UserMeResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str | None
    role: str
    preferred_lang: str
    orcid: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    # Workflow-email opt-out toggle. Defaults to True at the DB layer; old
    # clients that didn't read it can ignore the field. Transactional
    # emails (password reset) ignore this flag.
    email_notifications_enabled: bool = True
    created_at: str
    last_login_at: str | None

    model_config = {"from_attributes": True}


class UserMeUpdate(BaseModel):
    """Self-service patch for the authenticated user.

    Only exposes fields the user can safely change about themselves.
    Email, password and role transitions stay on dedicated flows.
    Pass ``orcid=""`` to clear the stored ORCID; pass ``bio=""`` to
    clear the stored bio.
    """

    display_name: str | None = Field(default=None, max_length=128)
    preferred_lang: str | None = None
    orcid: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    # ``None`` means "leave unchanged"; the patch handler distinguishes
    # via ``model_fields_set`` so a missing field never accidentally
    # silences workflow notifications.
    email_notifications_enabled: bool | None = None

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
            return ""  # sentinel meaning "clear"
        if not is_valid_orcid(cleaned):
            raise ValueError(
                "orcid must be in the form XXXX-XXXX-XXXX-XXXX with a valid checksum"
            )
        return cleaned
