"""Celery application (ADR-006). Dedicated queues per workload; beat drives re-syncs."""

from __future__ import annotations

from celery import Celery

from ordy_workers.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "ordy",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    include=["ordy_workers.ingestion.tasks", "ordy_workers.retention"],
)

celery_app.conf.update(
    task_default_queue="ingestion",
    task_routes={
        "ordy.ingestion.*": {"queue": "ingestion"},
        "ordy.embeddings.*": {"queue": "embeddings"},
        "ordy.webhooks.*": {"queue": "webhooks"},
        "ordy.retention.*": {"queue": "maintenance"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    timezone="UTC",
)

# Scheduled re-crawls (doc 04 §2.9). The beat task enqueues per-source runs.
celery_app.conf.beat_schedule = {
    "resync-due-sources": {
        "task": "ordy.ingestion.enqueue_due_resyncs",
        "schedule": 3600.0,  # hourly sweep; per-source cron honored inside
    },
    "enforce-retention": {
        "task": "ordy.retention.enforce",
        "schedule": 86400.0,  # nightly (doc 06 §5)
    },
}
