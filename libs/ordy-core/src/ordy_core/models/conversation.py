"""Agent config + conversation models (doc 06 §3.4). Tenant-owned → RLS.

``conversation_turns`` is a plain table here; the monthly range-partitioning from
doc 06 §5 is applied as a production infra migration (deferred; does not change the
application-visible shape).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ordy_core.db.base import Base, TenantMixin, TimestampMixin, pk
from ordy_core.enums import Channel, ConversationStatus, TurnRole


class AgentConfig(Base, TenantMixin, TimestampMixin):
    __tablename__ = "agent_configs"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(Text, default="Default agent", nullable=False)
    persona: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    voice: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), default=lambda: ["fr"], nullable=False)
    escalation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    model_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column()


class Conversation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = pk()
    agent_config_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_configs.id", ondelete="SET NULL")
    )
    # FK to customers lands in Phase 7; kept as a nullable id until then.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    channel: Mapped[Channel] = mapped_column(default=Channel.SANDBOX, nullable=False)
    pipeline_mode: Mapped[str | None] = mapped_column(Text)  # realtime | modular | text
    language: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ConversationStatus] = mapped_column(default=ConversationStatus.ACTIVE, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class ConversationTurn(Base, TenantMixin, TimestampMixin):
    __tablename__ = "conversation_turns"

    id: Mapped[uuid.UUID] = pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[TurnRole] = mapped_column(nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    content_json: Mapped[dict | None] = mapped_column(JSONB)
    audio_object_key: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
