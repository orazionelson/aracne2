from pydantic import BaseModel, field_validator


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
    token_type: str = "bearer"


class UserMeResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str | None
    role: str
    preferred_lang: str
    created_at: str
    last_login_at: str | None

    model_config = {"from_attributes": True}
