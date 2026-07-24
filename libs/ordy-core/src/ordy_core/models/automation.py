"""Browser automation workflows + runs (doc 06 §3.7).

Workflows are approved artifacts: generated at onboarding, dry-run verified, human
approved, then replayed deterministically. Every run stores per-step results and an
artifacts prefix (screenshots + DOM snapshots, field-masked).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ordy_core.db.base import Base, TenantMixin, TimestampMixin, pk
from ordy_core.enums import WorkflowStatus


class AutomationWorkflow(Base, TenantMixin, TimestampMixin):
    __tablename__ = "automation_workflows"

    id: Mapped[uuid.UUID] = pk()
    action_key: Mapped[str] = mapped_column(Text, nullable=False)  # tool this implements
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    target_domain: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)  # doc 04 §6 step format
    status: Mapped[WorkflowStatus] = mapped_column(default=WorkflowStatus.DRAFT, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column()
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_from: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column()


class AutomationRun(Base, TenantMixin, TimestampMixin):
    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = pk()
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("automation_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_execution_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text, default="live", nullable=False)  # live | dry_run | verification
    status: Mapped[str] = mapped_column(Text, default="queued", nullable=False)
    current_step: Mapped[int | None] = mapped_column(Integer)
    step_results: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    artifacts_prefix: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
