"""Application settings, loaded from environment variables (prefix ``VIA_``).

Secrets are only ever read from the environment; see ``.env.example`` for the
full list and docs/SECURITY.md for the rules.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_SECRETS = {"", "change-me", "changeme", "secret"}


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class StorageBackendName(StrEnum):
    S3 = "s3"
    LOCAL = "local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIA_", env_file=".env", extra="ignore")

    env: Environment = Environment.DEVELOPMENT
    secret_key: SecretStr = SecretStr("change-me")
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://via:via@localhost:5432/via"
    database_pool_size: int = 5
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])

    storage_backend: StorageBackendName = StorageBackendName.S3
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "via-designs"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_auto_create_bucket: bool = False
    local_storage_path: Path = Path("./data/storage")

    #: Comma-separated proxy IPs whose X-Forwarded-For is trusted (the web container in Compose).
    forwarded_allow_ips: str = "127.0.0.1"

    max_upload_bytes: int = 50 * 1024 * 1024
    #: Wall-clock limit for one parse; CPU time is limited to the same number of seconds.
    parser_timeout_seconds: int = 60
    #: Address-space limit for the parser subprocess.
    parser_memory_limit_mb: int = 1024
    #: Redis queue used for PCB import jobs.
    import_queue_name: str = "via-pcb-import"
    enable_docs: bool = True

    # --- Sessions & auth ---------------------------------------------------
    session_cookie_name: str = "via_session"
    session_ttl_hours: int = 24 * 14
    #: None = Secure cookies in production only.
    session_cookie_secure: bool | None = None
    password_reset_ttl_minutes: int = 60
    #: Public URL of the web app, used to build links in emails (password reset).
    public_web_url: str = "http://localhost:3000"
    rate_limit_enabled: bool = True

    @property
    def cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.env == Environment.PRODUCTION

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _production_safety(self) -> Settings:
        if self.env == Environment.PRODUCTION:
            if self.secret_key.get_secret_value() in _INSECURE_SECRETS or len(self.secret_key.get_secret_value()) < 32:
                raise ValueError("VIA_SECRET_KEY must be set to a random value of at least 32 characters in production")
            if "*" in self.cors_origins:
                raise ValueError("VIA_CORS_ORIGINS must not contain '*' in production")
            if self.s3_auto_create_bucket:
                raise ValueError("VIA_S3_AUTO_CREATE_BUCKET is a development convenience; provision buckets explicitly")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
