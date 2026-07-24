"""DB-backed NativeAdapter (doc 01 §4.8) — the Phase 7 body behind Phase 6's contract.

Every restaurant has this on day one: orders land in the Ordy dashboard even with zero
integrations, and it is the fallback when an integration breaks. Prices are re-derived
here from the menu snapshot the gate already validated — the adapter never trusts input
totals either.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from ordy_core.enums import Channel, OrderStatus, ReservationStatus, ServiceType
from ordy_core.models import Order, OrderEvent, OrderItem, Reservation
from ordy_orders.totals import compute_totals
from ordy_tools.pricing import ProductSnapshot, price_items
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DbNativeAdapter:
    """Writes real orders/reservations. Honors idempotency via the unique
    (restaurant_id, idempotency_key) constraint."""

    name = "native"

    def __init__(
        self,
        session: AsyncSession,
        restaurant_id: uuid.UUID,
        *,
        menu: dict[str, ProductSnapshot],
        currency: str = "TND",
        channel: Channel = Channel.SANDBOX,
        conversation_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        delivery_fee_minor: int = 0,
    ) -> None:
        self._session = session
        self._restaurant_id = restaurant_id
        self._menu = menu
        self._currency = currency
        self._channel = channel
        self._conversation_id = conversation_id
        self._customer_id = customer_id
        self._delivery_fee_minor = delivery_fee_minor

    async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
        if tool_key == "create_order":
            return await self._create_order(args, idempotency_key)
        if tool_key == "make_reservation":
            return await self._make_reservation(args, idempotency_key)
        if tool_key == "cancel_order":
            return await self._cancel_order(args)
        if tool_key == "get_order_status":
            return await self._order_status(args)
        if tool_key == "check_availability":
            product = self._menu.get(str(args.get("product_id")))
            return {"available": bool(product and product.is_available)}
        return {"acknowledged": True}

    # ---- orders ----

    async def _create_order(self, args: dict, idempotency_key: str) -> dict:
        existing = await self._session.scalar(
            select(Order).where(
                Order.restaurant_id == self._restaurant_id, Order.idempotency_key == idempotency_key
            )
        )
        if existing is not None:  # replay → same order, never a duplicate
            return {
                "order_id": str(existing.tracking_token or existing.id),
                "status": "confirmed",
                "total_minor": existing.total_minor,
                "currency": existing.currency,
            }

        pricing = price_items(args.get("items", []), self._menu)
        if not pricing.ok:
            raise ValueError(f"{pricing.error_code}: {pricing.error_message}")

        order_type = ServiceType(args.get("type", "pickup"))
        fee = self._delivery_fee_minor if order_type is ServiceType.DELIVERY else 0
        totals = compute_totals(pricing.total_minor, delivery_fee_minor=fee)

        order = Order(
            restaurant_id=self._restaurant_id,
            customer_id=self._customer_id,
            conversation_id=self._conversation_id,
            channel=self._channel,
            type=order_type,
            status=OrderStatus.CONFIRMED,
            subtotal_minor=totals.subtotal_minor,
            discount_minor=totals.discount_minor,
            delivery_fee_minor=totals.delivery_fee_minor,
            total_minor=totals.total_minor,
            currency=self._currency,
            address=args.get("address"),
            scheduled_for=args.get("scheduled_for"),
            executed_via="native",
            idempotency_key=idempotency_key,
            tracking_token=secrets.token_urlsafe(12),
            note=args.get("note"),
        )
        self._session.add(order)
        await self._session.flush()

        for item in pricing.items:
            self._session.add(
                OrderItem(
                    restaurant_id=self._restaurant_id,
                    order_id=order.id,
                    product_id=uuid.UUID(item.product_id),
                    variant_id=uuid.UUID(item.variant_id) if item.variant_id else None,
                    name_snapshot=item.label(),
                    unit_price_minor=item.unit_price_minor,
                    quantity=item.quantity,
                    total_minor=item.total_minor,
                )
            )
        self._session.add(
            OrderEvent(
                restaurant_id=self._restaurant_id,
                order_id=order.id,
                type="created",
                actor={"kind": "agent", "conversation_id": str(self._conversation_id or "")},
                data={"total_minor": order.total_minor, "currency": order.currency},
            )
        )
        return {
            "order_id": order.tracking_token or str(order.id),
            "status": "confirmed",
            "total_minor": order.total_minor,
            "currency": order.currency,
            "eta_minutes": 20,
        }

    async def _cancel_order(self, args: dict) -> dict:
        order = await self._find_order(str(args.get("order_ref", "")))
        if order is not None and order.status not in {OrderStatus.COMPLETED, OrderStatus.CANCELLED}:
            order.status = OrderStatus.CANCELLED
            self._session.add(
                OrderEvent(
                    restaurant_id=self._restaurant_id, order_id=order.id, type="cancelled",
                    actor={"kind": "agent"}, data={"reason": args.get("reason")},
                )
            )
        return {"cancelled": True}

    async def _order_status(self, args: dict) -> dict:
        order = await self._find_order(str(args.get("order_ref", "")))
        return {"status": order.status.value if order else "unknown"}

    async def _find_order(self, ref: str) -> Order | None:
        return await self._session.scalar(
            select(Order).where(
                Order.restaurant_id == self._restaurant_id, Order.tracking_token == ref
            )
        )

    # ---- reservations ----

    async def _make_reservation(self, args: dict, idempotency_key: str) -> dict:
        existing = await self._session.scalar(
            select(Reservation).where(
                Reservation.restaurant_id == self._restaurant_id,
                Reservation.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return {"reservation_id": str(existing.id), "status": existing.status.value}

        starts_at = args.get("starts_at")
        if isinstance(starts_at, str):
            starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        reservation = Reservation(
            restaurant_id=self._restaurant_id,
            customer_id=self._customer_id,
            conversation_id=self._conversation_id,
            party_size=int(args.get("party_size", 1)),
            starts_at=starts_at or datetime.now(UTC),
            status=ReservationStatus.CONFIRMED,
            note=args.get("note"),
            executed_via="native",
            idempotency_key=idempotency_key,
        )
        self._session.add(reservation)
        await self._session.flush()
        return {"reservation_id": str(reservation.id), "status": "confirmed"}
