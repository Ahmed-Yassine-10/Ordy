"""Typed application settings (12-factor, env-driven)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://ordy_app:ordy_app_pw@localhost:5432/ordy"
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    # Ingestion (Phase 3). Inline runs the pipeline in-process (dev, no broker needed);
    # otherwise runs are enqueued to the Celery worker.
    ingest_inline: bool = True
    storage_local_dir: str = "./volumes/objects"

    jwt_secret: str = "dev-only-change-me"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2_592_000
    jwt_issuer: str = "ordy"

    web_origin: str = "http://localhost:3000"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
