"""DB-bound orchestration: run a source through the pipeline and persist drafts.

Kept out of ``ordy_ingest/__init__`` so the pure stages stay importable without
SQLAlchemy. Both the Celery worker and the API's inline-dev path call ``execute_run``.
Publishing approved drafts into the live menu is a separate, human-triggered step in
the API (ADR-012) — this stage only ever writes *drafts*.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from ordy_core.db import Database, TenantContext
from ordy_core.enums import DocStatus, DocType, MapStatus, RunStatus
from ordy_core.models import (
    CapabilityMap,
    IngestionRun,
    KnowledgeDocument,
    KnowledgeSource,
    Restaurant,
)
from ordy_core.storage import ObjectStore, tenant_prefix
from sqlalchemy import func, select

from ordy_ingest.diff import content_hash
from ordy_ingest.fetch import Fetcher
from ordy_ingest.models import to_jsonable
from ordy_ingest.orchestrator import run_pipeline


def _now() -> datetime:
    return datetime.now(UTC)


def _render_markdown(bundle: dict) -> str:
    lines = ["# Menu (extracted draft)"]
    by_cat: dict[str, list[dict]] = {}
    for item in bundle.get("items", []):
        by_cat.setdefault(item.get("category") or "Menu", []).append(item)
    for cat, items in by_cat.items():
        lines.append(f"\n## {cat}")
        for it in items:
            if it.get("variants"):
                variants = ", ".join(f"{v['name']} {v['price_minor']}" for v in it["variants"])
                lines.append(f"- {it['name']} ({variants})")
            else:
                price = it.get("price_minor")
                lines.append(f"- {it['name']}" + (f" — {price}" if price is not None else " — (price?)"))
    return "\n".join(lines)


async def execute_run(
    db: Database,
    storage: ObjectStore,
    *,
    run_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    make_fetcher: Callable[[str, dict], Fetcher],
    max_pages: int = 50,
) -> None:
    """``make_fetcher(kind, config)`` builds the transport for the source kind — a
    Playwright/HTTP fetcher in the worker, a fixture fetcher in tests."""
    ctx = TenantContext(restaurant_id=restaurant_id)

    # 1) Load the source + restaurant currency; mark the run started.
    async with db.session(ctx) as s:
        run = await s.get(IngestionRun, run_id)
        if run is None:
            raise LookupError(f"ingestion run {run_id} not found")
        source = await s.get(KnowledgeSource, run.source_id)
        restaurant = await s.get(Restaurant, restaurant_id)
        kind = source.kind.value
        config = dict(source.config)
        currency = restaurant.currency if restaurant else "TND"
        prefix = tenant_prefix(str(restaurant_id), "ingest", str(run_id))
        run.status = RunStatus.FETCHING
        run.started_at = _now()
        run.artifacts_prefix = prefix

    # 2) Heavy work (crawl + extract + analyze). Pure pipeline; no DB held.
    try:
        fetcher = make_fetcher(kind, config)
        output = run_pipeline(
            kind=kind, config=config, fetcher=fetcher, currency=currency, max_pages=max_pages
        )
    except Exception as exc:  # noqa: BLE001 — record and surface as a failed run
        async with db.session(ctx) as s:
            run = await s.get(IngestionRun, run_id)
            run.status = RunStatus.FAILED
            run.error = {"type": type(exc).__name__, "message": str(exc)}
            run.finished_at = _now()
        raise

    bundle_json = to_jsonable(output.bundle)
    storage.put_json(f"{prefix}/bundle.json", bundle_json)
    storage.put_json(f"{prefix}/capability_map.json", output.capability_map)

    # 3) Persist drafts + capability map; hand off to human review.
    async with db.session(ctx) as s:
        run = await s.get(IngestionRun, run_id)
        markdown = _render_markdown(bundle_json)

        s.add(
            KnowledgeDocument(
                restaurant_id=restaurant_id,
                source_id=run.source_id,
                run_id=run_id,
                doc_type=DocType.MENU,
                title="Menu (draft)",
                content=markdown,
                content_hash=content_hash(markdown),
                status=DocStatus.DRAFT,
                draft=bundle_json,
                provenance={"generated_from_run": str(run_id)},
            )
        )

        next_version = (
            await s.scalar(
                select(func.coalesce(func.max(CapabilityMap.version), 0)).where(
                    CapabilityMap.restaurant_id == restaurant_id
                )
            )
        ) + 1
        cap = dict(output.capability_map)
        cap["version"] = next_version
        s.add(
            CapabilityMap(
                restaurant_id=restaurant_id,
                version=next_version,
                map=cap,
                status=MapStatus.DRAFT,
                generated_from=run_id,
            )
        )

        run.status = RunStatus.AWAITING_REVIEW
        run.finished_at = _now()
        run.stats = {**output.bundle.stats, "pages_fetched": output.pages_fetched, "warnings": output.warnings}
