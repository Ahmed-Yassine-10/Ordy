"""Knowledge & ingestion service.

Trigger runs (inline in dev, or enqueued to the worker), serve the review payload,
and — on explicit human approval — publish drafts into the live menu tables. Prices
reach the menu only through ``publish_review`` (ADR-012).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ordy_core.db import Database, TenantContext
from ordy_core.enums import (
    DocStatus,
    DocType,
    IngestionTrigger,
    MapStatus,
    MenuStatus,
    ProductStatus,
    RunStatus,
    SourceKind,
)
from ordy_core.errors import NotFound, ValidationFailed
from ordy_core.models import (
    CapabilityMap,
    IngestionRun,
    KnowledgeDocument,
    KnowledgeSource,
    Menu,
    MenuCategory,
    Product,
    ProductVariant,
    Restaurant,
)
from ordy_core.storage import LocalObjectStore
from ordy_ingest.fetch import Fetcher, StaticFetcher
from ordy_ingest.runner import execute_run
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.config import Settings
from ordy_api.modules.knowledge.schemas import PublishResult, ReviewSubmit


def _now() -> datetime:
    return datetime.now(UTC)


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


# ---- sources ----

async def create_source(
    session: AsyncSession, restaurant_id: uuid.UUID, *, kind: SourceKind, config: dict, schedule: str | None
) -> KnowledgeSource:
    if kind in {SourceKind.WEBSITE, SourceKind.API_DOC} and not config.get("url"):
        raise ValidationFailed(f"'url' is required in config for source kind '{kind.value}'")
    source = KnowledgeSource(restaurant_id=restaurant_id, kind=kind, config=config, schedule=schedule)
    session.add(source)
    await session.flush()
    return source


async def list_sources(session: AsyncSession, restaurant_id: uuid.UUID) -> list[KnowledgeSource]:
    rows = await session.scalars(
        select(KnowledgeSource)
        .where(KnowledgeSource.restaurant_id == restaurant_id)
        .order_by(KnowledgeSource.created_at.desc())
    )
    return list(rows)


# ---- runs ----

def _inline_fetcher(kind: str, config: dict) -> Fetcher:
    return StaticFetcher()


async def trigger_run(
    db: Database,
    ctx: TenantContext,
    settings: Settings,
    *,
    source_id: uuid.UUID,
    trigger: IngestionTrigger = IngestionTrigger.MANUAL,
) -> IngestionRun:
    restaurant_id = ctx.restaurant_id
    assert restaurant_id is not None

    async with db.session(ctx) as s:
        source = await s.get(KnowledgeSource, source_id)
        if source is None:
            raise NotFound("source not found")
        run = IngestionRun(
            restaurant_id=restaurant_id, source_id=source_id, trigger=trigger, status=RunStatus.QUEUED
        )
        s.add(run)
        await s.flush()
        run_id = run.id

    # The run row is now committed and visible to a separate session/worker.
    if settings.ingest_inline:
        storage = LocalObjectStore(settings.storage_local_dir)
        try:
            await execute_run(
                db, storage, run_id=run_id, restaurant_id=restaurant_id, make_fetcher=_inline_fetcher
            )
        except Exception:  # noqa: BLE001 — run is marked FAILED inside execute_run
            pass
    else:
        from ordy_api.celery_client import enqueue_ingestion

        enqueue_ingestion(str(run_id), str(restaurant_id))

    async with db.session(ctx) as s:
        return await s.get(IngestionRun, run_id)  # type: ignore[return-value]


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> IngestionRun:
    run = await session.get(IngestionRun, run_id)
    if run is None:
        raise NotFound("ingestion run not found")
    return run


async def get_review(
    session: AsyncSession, run_id: uuid.UUID
) -> tuple[IngestionRun, dict | None, dict | None]:
    run = await get_run(session, run_id)
    menu_doc = await session.scalar(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.run_id == run_id, KnowledgeDocument.doc_type == DocType.MENU)
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(1)
    )
    cap = await session.scalar(
        select(CapabilityMap)
        .where(CapabilityMap.generated_from == run_id)
        .order_by(CapabilityMap.version.desc())
        .limit(1)
    )
    return run, (menu_doc.draft if menu_doc else None), (cap.map if cap else None)


# ---- publish (human-approved) ----

async def _default_menu(session: AsyncSession, restaurant_id: uuid.UUID) -> Menu:
    menu = await session.scalar(
        select(Menu).where(Menu.restaurant_id == restaurant_id).limit(1)
    )
    if menu is None:
        menu = Menu(restaurant_id=restaurant_id, status=MenuStatus.PUBLISHED)
        session.add(menu)
        await session.flush()
    return menu


async def publish_review(
    session: AsyncSession,
    restaurant_id: uuid.UUID,
    run_id: uuid.UUID,
    payload: ReviewSubmit,
    *,
    user_id: uuid.UUID | None,
) -> PublishResult:
    run = await get_run(session, run_id)
    if run.status not in {RunStatus.AWAITING_REVIEW, RunStatus.PUBLISHED}:
        raise ValidationFailed(f"run is not reviewable (status={run.status.value})")

    restaurant = await session.get(Restaurant, restaurant_id)
    currency = restaurant.currency if restaurant else "TND"

    products = 0
    categories = 0
    if payload.approve_menu:
        menu_doc = await session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.run_id == run_id, KnowledgeDocument.doc_type == DocType.MENU)
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(1)
        )
        if menu_doc is not None:
            menu = await _default_menu(session, restaurant_id)
            cat_cache: dict[str, MenuCategory] = {}
            for item in menu_doc.draft.get("items", []):
                override = payload.overrides.get(_norm(item["name"])) or payload.overrides.get(item["name"])
                if override and override.exclude:
                    continue
                cat_name = (override.category if override else None) or item.get("category") or "Menu"
                if cat_name not in cat_cache:
                    category = MenuCategory(restaurant_id=restaurant_id, menu_id=menu.id, name=cat_name)
                    session.add(category)
                    await session.flush()
                    cat_cache[cat_name] = category
                    categories += 1
                category = cat_cache[cat_name]

                variants = item.get("variants") or []
                price = None if variants else (
                    override.price_minor if (override and override.price_minor is not None)
                    else item.get("price_minor")
                )
                product = Product(
                    restaurant_id=restaurant_id,
                    category_id=category.id,
                    name=item["name"],
                    currency=currency,
                    price_minor=price,
                    tags=item.get("tags", []),
                    allergens=item.get("allergens", []),
                    status=ProductStatus.PUBLISHED,
                    provenance=item.get("provenance") or {},
                )
                session.add(product)
                await session.flush()
                for v in variants:
                    session.add(
                        ProductVariant(
                            restaurant_id=restaurant_id,
                            product_id=product.id,
                            name=v["name"],
                            price_minor=int(v["price_minor"]),
                        )
                    )
                products += 1

            menu_doc.status = DocStatus.APPROVED
            menu_doc.approved_by = user_id
            menu_doc.approved_at = _now()

    activated = False
    if payload.approve_capability_map:
        cap = await session.scalar(
            select(CapabilityMap)
            .where(CapabilityMap.generated_from == run_id)
            .order_by(CapabilityMap.version.desc())
            .limit(1)
        )
        if cap is not None:
            # Supersede any currently-active map, then activate this one.
            actives = await session.scalars(
                select(CapabilityMap).where(
                    CapabilityMap.restaurant_id == restaurant_id,
                    CapabilityMap.status == MapStatus.ACTIVE,
                )
            )
            for existing in actives:
                existing.status = MapStatus.SUPERSEDED
            cap.status = MapStatus.ACTIVE
            cap.approved_by = user_id
            cap.approved_at = _now()
            activated = True

    run.status = RunStatus.PUBLISHED if (payload.approve_menu or payload.approve_capability_map) else RunStatus.REJECTED
    return PublishResult(
        published_products=products,
        published_categories=categories,
        capability_map_activated=activated,
        run_status=run.status,
    )


async def list_capability_maps(session: AsyncSession, restaurant_id: uuid.UUID) -> list[CapabilityMap]:
    rows = await session.scalars(
        select(CapabilityMap)
        .where(CapabilityMap.restaurant_id == restaurant_id)
        .order_by(CapabilityMap.version.desc())
    )
    return list(rows)
