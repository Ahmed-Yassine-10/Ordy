from __future__ import annotations

import uuid
from datetime import datetime

from ordy_core.enums import (
    DocStatus,
    IngestionTrigger,
    MapStatus,
    RunStatus,
    SourceKind,
    SourceStatus,
)
from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    kind: SourceKind
    # For website/api_doc: {"url": "..."}. Secrets (db/github) go in as vault refs.
    config: dict = Field(default_factory=dict)
    schedule: str | None = None  # cron for re-sync


class SourceOut(BaseModel):
    id: uuid.UUID
    kind: SourceKind
    config: dict
    status: SourceStatus
    schedule: str | None
    last_synced_at: datetime | None


class RunOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    trigger: IngestionTrigger
    status: RunStatus
    stats: dict
    error: dict | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    doc_type: str
    title: str
    status: DocStatus
    content: str
    url: str | None
    created_at: datetime


class ReviewData(BaseModel):
    """Everything the reviewer needs (doc 04 §2.7)."""

    run: RunOut
    menu_draft: dict | None  # the extracted DraftBundle payload
    capability_map: dict | None
    warnings: list[str] = Field(default_factory=list)


class ItemOverride(BaseModel):
    price_minor: int | None = Field(default=None, ge=0)
    category: str | None = None
    exclude: bool = False


class ReviewSubmit(BaseModel):
    approve_menu: bool = True
    # keyed by item name (normalized server-side)
    overrides: dict[str, ItemOverride] = Field(default_factory=dict)
    approve_capability_map: bool = True


class PublishResult(BaseModel):
    published_products: int
    published_categories: int
    capability_map_activated: bool
    run_status: RunStatus


class CapabilityMapOut(BaseModel):
    id: uuid.UUID
    version: int
    status: MapStatus
    map: dict
