"""Orders + reservations API (doc 07 §2.7).

Staff status changes go through the SAME state machine the agent does — there is one set
of rules, not a strict path for the agent and a loose one for humans.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from ordy_core.enums import MemberRole, OrderStatus, ReservationStatus
from ordy_core.errors import NotFound, ValidationFailed
from ordy_core.models import Order, OrderEvent, OrderItem, Reservation
from ordy_orders.state import (
    InvalidTransition,
    assert_reservation_transition,
    assert_transition,
    next_states,
)
from pydantic import BaseModel
from sqlalchemy import select

from ordy_api.deps import Scope, require_tenant

router = APIRouter(prefix="/restaurants/{restaurant_id}", tags=["orders"])
public_router = APIRouter(prefix="/public", tags=["public"])


class OrderItemOut(BaseModel):
    name: str
    quantity: int
    unit_price_minor: int
    total_minor: int


class OrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    type: str
    channel: str
    subtotal_minor: int
    delivery_fee_minor: int
    discount_minor: int
    total_minor: int
    currency: str
    tracking_token: str | None
    executed_via: str
    created_at: datetime
    next_states: list[str] = []
    items: list[OrderItemOut] = []


class StatusChange(BaseModel):
    status: OrderStatus


class ReservationOut(BaseModel):
    id: uuid.UUID
    party_size: int
    starts_at: datetime
    status: ReservationStatus
    note: str | None


class ReservationStatusChange(BaseModel):
    status: ReservationStatus


class TrackingOut(BaseModel):
    status: OrderStatus
    total_minor: int
    currency: str
    placed_at: datetime


def _rid(scope: Scope) -> uuid.UUID:
    assert scope.restaurant_id is not None
    return scope.restaurant_id


async def _load_order(scope: Scope, order_id: uuid.UUID) -> Order:
    order = await scope.session.get(Order, order_id)
    if order is None or order.restaurant_id != _rid(scope):
        raise NotFound("order not found")
    return order


def _to_out(order: Order, items: list[OrderItem]) -> OrderOut:
    return OrderOut(
        id=order.id,
        status=order.status,
        type=order.type.value,
        channel=order.channel.value,
        subtotal_minor=order.subtotal_minor,
        delivery_fee_minor=order.delivery_fee_minor,
        discount_minor=order.discount_minor,
        total_minor=order.total_minor,
        currency=order.currency,
        tracking_token=order.tracking_token,
        executed_via=order.executed_via,
        created_at=order.created_at,
        next_states=[s.value for s in next_states(order.status)],
        items=[
            OrderItemOut(
                name=i.name_snapshot, quantity=i.quantity,
                unit_price_minor=i.unit_price_minor, total_minor=i.total_minor,
            )
            for i in items
        ],
    )


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    status: OrderStatus | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    scope: Scope = Depends(require_tenant(MemberRole.STAFF)),
) -> list[OrderOut]:
    """The live operations feed — newest first, optionally filtered by status."""
    query = select(Order).where(Order.restaurant_id == _rid(scope))
    if status is not None:
        query = query.where(Order.status == status)
    orders = list(await scope.session.scalars(query.order_by(Order.created_at.desc()).limit(limit)))
    if not orders:
        return []

    items = list(
        await scope.session.scalars(
            select(OrderItem).where(OrderItem.order_id.in_([o.id for o in orders]))
        )
    )
    by_order: dict[uuid.UUID, list[OrderItem]] = {}
    for item in items:
        by_order.setdefault(item.order_id, []).append(item)
    return [_to_out(o, by_order.get(o.id, [])) for o in orders]


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.STAFF))
) -> OrderOut:
    order = await _load_order(scope, order_id)
    items = list(await scope.session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    return _to_out(order, items)


@router.post("/orders/{order_id}/status", response_model=OrderOut)
async def change_order_status(
    order_id: uuid.UUID,
    body: StatusChange,
    scope: Scope = Depends(require_tenant(MemberRole.STAFF)),
) -> OrderOut:
    order = await _load_order(scope, order_id)
    try:
        assert_transition(order.status, body.status)
    except InvalidTransition as exc:
        raise ValidationFailed(str(exc)) from exc

    previous = order.status
    order.status = body.status
    scope.session.add(
        OrderEvent(
            restaurant_id=_rid(scope),
            order_id=order.id,
            type="status_changed",
            actor={"kind": "staff", "id": str(scope.principal.user_id or "")},
            data={"from": previous.value, "to": body.status.value, "at": datetime.now(UTC).isoformat()},
        )
    )
    items = list(await scope.session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    return _to_out(order, items)


@router.get("/reservations", response_model=list[ReservationOut])
async def list_reservations(
    scope: Scope = Depends(require_tenant(MemberRole.STAFF)),
    limit: int = Query(default=100, le=200),
) -> list[ReservationOut]:
    rows = await scope.session.scalars(
        select(Reservation)
        .where(Reservation.restaurant_id == _rid(scope))
        .order_by(Reservation.starts_at)
        .limit(limit)
    )
    return [ReservationOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/reservations/{reservation_id}/status", response_model=ReservationOut)
async def change_reservation_status(
    reservation_id: uuid.UUID,
    body: ReservationStatusChange,
    scope: Scope = Depends(require_tenant(MemberRole.STAFF)),
) -> ReservationOut:
    reservation = await scope.session.get(Reservation, reservation_id)
    if reservation is None or reservation.restaurant_id != _rid(scope):
        raise NotFound("reservation not found")
    try:
        assert_reservation_transition(reservation.status, body.status)
    except InvalidTransition as exc:
        raise ValidationFailed(str(exc)) from exc
    reservation.status = body.status
    return ReservationOut.model_validate(reservation, from_attributes=True)


@public_router.get("/orders/{tracking_token}", response_model=TrackingOut)
async def track_order(tracking_token: str, scope: Scope = Depends(require_tenant(MemberRole.VIEWER))) -> TrackingOut:
    """Customer-facing order status by opaque token (doc 07 §3).

    Note: bound to the tenant scope for now; the unauthenticated public variant lands
    with the widget's public surface.
    """
    order = await scope.session.scalar(
        select(Order).where(
            Order.restaurant_id == _rid(scope), Order.tracking_token == tracking_token
        )
    )
    if order is None:
        raise NotFound("order not found")
    return TrackingOut(
        status=order.status,
        total_minor=order.total_minor,
        currency=order.currency,
        placed_at=order.created_at,
    )
