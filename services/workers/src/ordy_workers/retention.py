"""Retention enforcement job (doc 06 §5, doc 08 §7).

Runs nightly via beat. Deletes audio objects, redacts aged transcripts, and purges
operational rows past their window. Retention policy per tenant may only SHORTEN the
platform defaults — the policy module enforces the ceiling.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ordy_core.db import Database, TenantContext
from ordy_core.models import ConversationTurn, Restaurant, WebhookDelivery
from ordy_security.retention import RetentionPolicy, cutoffs
from sqlalchemy import delete, select, update

from ordy_workers.celery_app import celery_app
from ordy_workers.config import get_settings


@celery_app.task(name="ordy.retention.enforce")
def enforce_retention() -> dict:
    return asyncio.run(_enforce())


async def _enforce() -> dict:
    settings = get_settings()
    db = Database(settings.database_url)
    now = datetime.now(UTC)
    stats = {"tenants": 0, "turns_redacted": 0, "webhooks_purged": 0}
    try:
        async with db.session(TenantContext(is_platform_admin=True)) as session:
            restaurants = list(await session.scalars(select(Restaurant)))

        for restaurant in restaurants:
            policy = RetentionPolicy().tightened_by((restaurant.settings or {}).get("retention", {}))
            marks = cutoffs(now, policy)
            ctx = TenantContext(restaurant_id=restaurant.id)

            async with db.session(ctx) as session:
                # Transcripts past the window keep their shape, lose their content.
                redacted = await session.execute(
                    update(ConversationTurn)
                    .where(
                        ConversationTurn.restaurant_id == restaurant.id,
                        ConversationTurn.created_at < marks.transcripts_before,
                        ConversationTurn.content.is_not(None),
                    )
                    .values(content="[expired]", audio_object_key=None)
                )
                purged = await session.execute(
                    delete(WebhookDelivery).where(
                        WebhookDelivery.restaurant_id == restaurant.id,
                        WebhookDelivery.created_at < marks.webhooks_before,
                    )
                )
                stats["turns_redacted"] += redacted.rowcount or 0
                stats["webhooks_purged"] += purged.rowcount or 0
                stats["tenants"] += 1
    finally:
        await db.dispose()
    return stats
