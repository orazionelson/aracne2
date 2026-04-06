from typing import Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_list_separator=",",
    )

    # PostgreSQL
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # eXist-db
    existdb_url: str
    existdb_user: str
    exist_password: str  # shared with the existdb Docker image (EXIST_PASSWORD)

    # JWT
    jwt_secret: str
    jwt_access_expiry_minutes: int = 60
    jwt_refresh_expiry_days: int = 30

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 64:
            raise ValueError("JWT_SECRET must be at least 64 characters")
        return v

    # Security
    bcrypt_rounds: int = 12
    cors_origins: list[str] = ["http://localhost:5173"]

    # Application
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    platform_name: str = "Aracne2"
    public_registration: bool = False
    max_upload_size_mb: int = 50

    # Admin seed — required only for `make seed`; None skips admin creation with warning
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str | None = None

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


# Singleton — import everywhere with: from app.config import settings
settings = Settings()
