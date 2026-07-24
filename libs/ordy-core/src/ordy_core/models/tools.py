"""Tool catalog, per-tenant enablement, and the action audit (doc 06 §3.6).

``tool_definitions`` is GLOBAL (platform catalog, seeded by migration — tools ship via
code review, never at conversation time). ``restaurant_tools`` is the tenant whitelist:
the only path to execution. ``action_executions`` is append-only audit — every proposal,
rejection, confirmation, and execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ordy_core.db.base import Base, TenantMixin, TimestampMixin, pk
from ordy_core.enums import ActionStatus, RiskLevel


class ToolDefinition(Base, TimestampMixin):
    """GLOBAL platform catalog — no tenant column, seeded from ordy_tools.catalog."""

    __tablename__ = "tool_definitions"
    __table_args__ = (UniqueConstraint("key", "version"),)

    id: Mapped[uuid.UUID] = pk()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[RiskLevel] = mapped_column(nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    idempotent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validators: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    compensation: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RestaurantTool(Base, TenantMixin, TimestampMixin):
    """Tenant whitelist + adapter binding + caps. Caps may only TIGHTEN platform defaults."""

    __tablename__ = "restaurant_tools"
    __table_args__ = (UniqueConstraint("restaurant_id", "tool_definition_id"),)

    id: Mapped[uuid.UUID] = pk()
    tool_definition_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tool_definitions.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    adapter: Mapped[str] = mapped_column(Text, default="native", nullable=False)
    binding: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    caps: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: ["voice_web", "voice_phone", "text_widget", "sandbox"], nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column()


class ActionExecution(Base, TenantMixin, TimestampMixin):
    """Append-only action audit. Written by the gate itself, not by cooperative logging.

    Monthly range-partitioning (doc 06 §5) is a later production infra migration.
    """

    __tablename__ = "action_executions"

    id: Mapped[uuid.UUID] = pk()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    restaurant_tool_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    tool_key: Mapped[str] = mapped_column(Text, nullable=False)
    tool_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[ActionStatus] = mapped_column(nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # redacted per ToolSpec
    output: Mapped[dict | None] = mapped_column(JSONB)
    validation_report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    rejection_code: Mapped[str | None] = mapped_column(Text)
    confirmation: Mapped[dict | None] = mapped_column(JSONB)
    adapter: Mapped[str | None] = mapped_column(Text)
    external_ref: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[dict | None] = mapped_column(JSONB)
