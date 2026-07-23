"""Minimal Celery client for enqueuing worker tasks by name.

The API does NOT import the worker package (service→service boundary, doc 09 §2);
it dispatches by task name over the shared broker.
"""

from __future__ import annotations

from functools import lru_cache

from celery import Celery

from ordy_api.config import get_settings


@lru_cache
def get_celery() -> Celery:
    settings = get_settings()
    return Celery("ordy-api-client", broker=settings.redis_url)


def enqueue_ingestion(run_id: str, restaurant_id: str) -> None:
    get_celery().send_task("ordy.ingestion.run", args=[run_id, restaurant_id], queue="ingestion")
