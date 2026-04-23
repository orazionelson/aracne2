import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # PostgreSQL
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # pgvector — optional vector store used for RAG. When pgvector_host is empty
    # the backend skips all RAG machinery gracefully (no engine, no retrieval).
    pgvector_host: str = ""
    pgvector_port: int = 5432
    pgvector_db: str = "aracne2_vectors"
    pgvector_user: str = "aracne2"
    pgvector_password: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pgvector_url(self) -> str | None:
        if not self.pgvector_host:
            return None
        return (
            f"postgresql+asyncpg://{self.pgvector_user}:{self.pgvector_password}"
            f"@{self.pgvector_host}:{self.pgvector_port}/{self.pgvector_db}"
        )

    # eXist-db
    existdb_url: str
    existdb_user: str
    # Admin password — set manually in eXist-db and stored here.
    # Used by the backend exclusively for bootstrap operations (ensure_root, bootstrap_user).
    exist_password: str = ""
    # Runtime user password — password of the dedicated 'aracne' account created at bootstrap.
    # All post-bootstrap operations use this credential. If empty, bootstrap is skipped and
    # the runtime client falls back to admin credentials (not recommended for production).
    existdb_app_password: str = ""

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
    # Read as str to avoid pydantic-settings JSON pre-parsing of list fields;
    # exposed as list[str] via cors_origins computed_field below.
    cors_origins_raw: str = Field("http://localhost:5173", alias="cors_origins")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        v = self.cors_origins_raw.strip()
        if v.startswith("["):
            origins: list[str] = json.loads(v)
        else:
            origins = [o.strip() for o in v.split(",") if o.strip()]

        _localhost_hosts = {"localhost", "127.0.0.1", "::1"}

        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "CORS_ORIGINS must not contain '*' — list explicit origins. "
                    "Wildcard with allow_credentials=True violates the CORS spec "
                    "and credentials are never sent by browsers to a '*' origin."
                )
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError(
                    f"CORS origin {origin!r} must start with 'http://' or 'https://'. "
                    "Bare hostnames, 'null', 'file://', and other schemes are not allowed."
                )
            if self.environment == "production" and origin.startswith("http://"):
                host = urlparse(origin).hostname or ""
                if host not in _localhost_hosts:
                    raise ValueError(
                        f"CORS origin {origin!r} uses HTTP in production. "
                        "Only HTTPS origins are allowed in production "
                        "(localhost is exempt for internal tooling)."
                    )

        return origins

    # Application
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    platform_name: str = "Aracne2"
    public_registration: bool = False
    max_upload_size_mb: int = 50

    # TEI schema storage — filesystem directory for validation and CM5 schema files.
    # Defaults to /app/schemas, which is inside the backend volume mount and writable
    # in development. Override via SCHEMAS_DIR env variable in production to point
    # to a persistent volume (e.g. /data/schemas mounted via docker-compose).
    schemas_dir: Path = Path("/app/schemas")

    # Media storage — filesystem directory for uploaded platform assets (logo, etc.).
    # Defaults to /app/media. Override via MEDIA_DIR env variable in production.
    media_dir: Path = Path("/app/media")

    # Document media root — uploaded images associated with TEI documents.
    # Each document's images live under {documents_media_root}/{collection_slug}/{doc_filename}/
    # Defaults to /app/documents_media. Override via DOCUMENTS_MEDIA_ROOT in production.
    documents_media_root: Path = Path("/app/documents_media")

    # Websites static root — generated static sites are written here.
    # Each site occupies a subdirectory named after its slug.
    # Serve via nginx in production: location /sites/ { alias /app/sites/; }
    websites_root: Path = Path("/app/sites")

    # Search engines HTML root — built search pages are written here.
    # Each engine occupies a subdirectory named after its slug.
    # Serve via nginx in production: location /search-pages/ { alias /app/search-pages/; }
    search_engines_root: Path = Path("/app/search-pages")

    # Backup storage — ZIP archives created by the native Backup plugin.
    # Defaults to /app/backups. Override via BACKUP_ROOT env variable in production
    # to point to a persistent volume mounted outside the container.
    backup_root: Path = Path("/app/backups")

    # GeoNames API — used by /geonames/search to power Place-of-Publication autocomplete.
    # Register a free account at https://www.geonames.org/login and set this variable.
    geonames_username: str = "aracne"


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
