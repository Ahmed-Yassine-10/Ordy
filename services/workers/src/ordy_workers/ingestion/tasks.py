"""Ingestion Celery tasks. Thin wrappers over the shared ``ordy_ingest.runner``."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from ordy_core.db import Database, TenantContext
from ordy_core.enums import IngestionTrigger, RunStatus, SourceStatus
from ordy_core.models import IngestionRun, KnowledgeSource
from ordy_ingest.runner import execute_run
from sqlalchemy import select

from ordy_workers.celery_app import celery_app
from ordy_workers.config import get_settings
from ordy_workers.fetchers import build_fetcher
from ordy_workers.storage import build_storage


@celery_app.task(name="ordy.ingestion.run", bind=True, max_retries=2)
def run_ingestion(self, run_id: str, restaurant_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Execute one ingestion run to the awaiting-review stage."""
    return asyncio.run(_run(uuid.UUID(run_id), uuid.UUID(restaurant_id)))


async def _run(run_id: uuid.UUID, restaurant_id: uuid.UUID) -> dict:
    settings = get_settings()
    db = Database(settings.database_url)
    storage = build_storage(settings)
    try:
        await execute_run(
            db,
            storage,
            run_id=run_id,
            restaurant_id=restaurant_id,
            make_fetcher=build_fetcher,
            max_pages=settings.ingest_max_pages,
        )
        return {"run_id": str(run_id), "status": "awaiting_review"}
    finally:
        await db.dispose()


@celery_app.task(name="ordy.ingestion.enqueue_due_resyncs")
def enqueue_due_resyncs() -> dict:
    """Beat entrypoint: find sources due for re-sync and enqueue runs (doc 04 §2.9)."""
    return asyncio.run(_enqueue_due_resyncs())


async def _enqueue_due_resyncs() -> dict:
    settings = get_settings()
    db = Database(settings.database_url)
    enqueued = 0
    try:
        # Platform-admin context to sweep across tenants; per-source cron eval is TODO.
        async with db.session(TenantContext(is_platform_admin=True)) as s:
            sources = await s.scalars(
                select(KnowledgeSource).where(
                    KnowledgeSource.status == SourceStatus.ACTIVE,
                    KnowledgeSource.schedule.is_not(None),
                )
            )
            for source in sources:
                run = IngestionRun(
                    restaurant_id=source.restaurant_id,
                    source_id=source.id,
                    trigger=IngestionTrigger.SCHEDULED,
                    status=RunStatus.QUEUED,
                    created_at=datetime.now(UTC),
                )
                s.add(run)
                await s.flush()
                run_ingestion.delay(str(run.id), str(source.restaurant_id))
                enqueued += 1
    finally:
        await db.dispose()
    return {"enqueued": enqueued}
