"""
Application settings loaded from environment variables.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "R3"
    secret_key: str = Field(
        default="change-me-in-production-use-openssl-rand-hex-32",
        description="Secret for JWT signing and Fernet subkey derivation.",
    )
    access_token_expire_minutes: int = 60 * 24 * 7

    database_url: str = "postgresql+asyncpg://r3:r3@localhost:5432/r3"
    # SQLite for local tests
    use_sqlite: bool = Field(
        default=False, description="In-memory sqlite for tests (env: USE_SQLITE)"
    )

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional LDAP: leave empty to disable
    ldap_server_uri: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_base_dn: str = ""
    ldap_user_filter: str = "(uid={username})"

    default_sprint_lifecycle_days: int = 14
    first_admin_password: str = "changeme"
    first_admin_username: str = "admin"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_postgres_dsn(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        """Return parsed CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton for dependency injection."""
    return Settings()
