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
    created_at: str
    last_login_at: str | None

    model_config = {"from_attributes": True}


class UserMeUpdate(BaseModel):
    """Self-service patch for the authenticated user.

    Only exposes fields the user can safely change about themselves.
    Email, password and role transitions stay on dedicated flows.
    Pass ``orcid=""`` to clear the stored ORCID.
    """

    display_name: str | None = Field(default=None, max_length=128)
    preferred_lang: str | None = None
    orcid: str | None = Field(default=None, max_length=80)

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
