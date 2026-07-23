"""Build the ObjectStore from worker settings (local dir in dev, S3 in prod)."""

from __future__ import annotations

from ordy_core.storage import LocalObjectStore, ObjectStore

from ordy_workers.config import WorkerSettings


def build_storage(settings: WorkerSettings) -> ObjectStore:
    if settings.storage_backend == "local":
        return LocalObjectStore(settings.storage_local_dir)
    # S3 implementation (boto3) is added alongside staging infra; local backs dev.
    raise NotImplementedError(f"storage backend '{settings.storage_backend}' not wired yet")
