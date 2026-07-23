"""Declarative base + common mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ordy_core.ids import uuid7


class Base(DeclarativeBase):
    """Root of all ORM models."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """Every tenant-owned table carries ``restaurant_id`` and is protected by RLS.

    The FK is declared here; the RLS policy is created in the migration (doc 06 §4).
    """

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def pk() -> Mapped[uuid.UUID]:
    """UUIDv7 primary key column (app-generated, time-ordered)."""
    return mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)
