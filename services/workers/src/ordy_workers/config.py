from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://ordy_app:ordy_app_pw@localhost:5432/ordy"

    # Storage: local filesystem in dev, S3 in staging/prod.
    storage_backend: str = "local"  # local | s3
    storage_local_dir: str = "./volumes/objects"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "ordy-dev"
    s3_region: str = "eu-west-1"

    ingest_max_pages: int = 50


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
