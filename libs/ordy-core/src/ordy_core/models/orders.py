"""Customers, orders, reservations, hours, zones, webhooks, usage (doc 06 §3.2–3.3, §3.8).

Order line items snapshot their name/price so a later menu edit never rewrites history.
Money is integer minor units throughout.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ordy_core.db.base import Base, TenantMixin, TimestampMixin, pk
from ordy_core.enums import Channel, OrderStatus, ReservationStatus, ServiceType


class Customer(Base, TenantMixin, TimestampMixin):
    """Per-tenant, phone-keyed identity (ADR-013). No passwords to breach."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("restaurant_id", "phone_e164"),)

    id: Mapped[uuid.UUID] = pk()
    phone_e164: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    addresses: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    consent: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    anonymized_at: Mapped[datetime | None] = mapped_column()  # GDPR erasure marker


class Order(Base, TenantMixin, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "idempotency_key"),
        Index("orders_feed_idx", "restaurant_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = pk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    channel: Mapped[Channel] = mapped_column(default=Channel.SANDBOX, nullable=False)
    type: Mapped[ServiceType] = mapped_column(nullable=False)
    status: Mapped[OrderStatus] = mapped_column(default=OrderStatus.DRAFT, nullable=False)

    subtotal_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    discount_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    delivery_fee_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    address: Mapped[dict | None] = mapped_column(JSONB)  # snapshot for delivery
    scheduled_for: Mapped[datetime | None] = mapped_column()
    executed_via: Mapped[str] = mapped_column(Text, default="native", nullable=False)
    external_ref: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    tracking_token: Mapped[str | None] = mapped_column(Text, index=True)
    note: Mapped[str | None] = mapped_column(Text)


class OrderItem(Base, TenantMixin, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    modifiers_snapshot: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("quantity > 0", name="order_items_qty_positive"),)


class OrderEvent(Base, TenantMixin, TimestampMixin):
    """Per-order timeline — who changed what, when (staff, agent, system, api)."""

    __tablename__ = "order_events"

    id: Mapped[uuid.UUID] = pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Reservation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "idempotency_key"),
        Index("reservations_calendar_idx", "restaurant_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = pk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        default=ReservationStatus.PENDING_CONFIRMATION, nullable=False
    )
    table_preference: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    executed_via: Mapped[str] = mapped_column(Text, default="native", nullable=False)
    external_ref: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)


class OperatingHours(Base, TenantMixin, TimestampMixin):
    __tablename__ = "operating_hours"

    id: Mapped[uuid.UUID] = pk()
    service: Mapped[ServiceType] = mapped_column(nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon
    opens: Mapped[time] = mapped_column(Time, nullable=False)  # local to restaurants.timezone
    closes: Mapped[time] = mapped_column(Time, nullable=False)  # < opens ⇒ spans midnight
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="hours_dow_range"),
        UniqueConstraint("restaurant_id", "service", "day_of_week", "opens"),
    )


class DeliveryZoneRow(Base, TenantMixin, TimestampMixin):
    __tablename__ = "delivery_zones"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geometry: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {kind, center, radius_m|polygon}
    fee_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    min_order_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    eta_minutes: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WebhookEndpoint(Base, TenantMixin, TimestampMixin):
    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = pk()
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # envelope-encrypted
    events: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WebhookDelivery(Base, TenantMixin, TimestampMixin):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = pk()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column()
    last_response: Mapped[dict | None] = mapped_column(JSONB)


class UsageRecord(Base, TenantMixin, TimestampMixin):
    """Metering for billing AND margin (ADR-014) — same rows drive both."""

    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = pk()
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_minor: Mapped[int | None] = mapped_column(BigInteger)  # our vendor cost
    meta: Mapped[dict] = mapped_column("meta", JSONB, default=dict, nullable=False)
    occurred_on: Mapped[datetime] = mapped_column(nullable=False)
    __table_args__ = (Index("usage_rollup_idx", "restaurant_id", "metric", "occurred_on"),)
