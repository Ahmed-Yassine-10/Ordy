"""Data Subject Request endpoints (doc 08 §7) — GDPR Arts. 15 & 17.

Export returns the customer's data; erasure **anonymizes** so financial and audit records
keep their integrity. Both are owner-only and audited: exercising someone else's rights is
itself a privacy event.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from ordy_core.enums import MemberRole, TurnRole
from ordy_core.errors import NotFound
from ordy_core.models import Conversation, ConversationTurn, Customer, Order, OrderItem
from ordy_security.dsr import build_export, erase_customer
from pydantic import BaseModel
from sqlalchemy import select

from ordy_api.config import get_settings
from ordy_api.deps import Scope, require_tenant

router = APIRouter(prefix="/restaurants/{restaurant_id}/privacy", tags=["privacy"])


class ErasureResultOut(BaseModel):
    customer_id: uuid.UUID
    orders_stripped: int
    turns_redacted: int
    anonymized_at: datetime


def _rid(scope: Scope) -> uuid.UUID:
    assert scope.restaurant_id is not None
    return scope.restaurant_id


async def _load_customer(scope: Scope, customer_id: uuid.UUID) -> Customer:
    customer = await scope.session.get(Customer, customer_id)
    if customer is None or customer.restaurant_id != _rid(scope):
        raise NotFound("customer not found")
    return customer


async def _customer_orders(scope: Scope, customer_id: uuid.UUID) -> list[Order]:
    return list(
        await scope.session.scalars(
            select(Order).where(
                Order.restaurant_id == _rid(scope), Order.customer_id == customer_id
            )
        )
    )


@router.get("/customers/{customer_id}/export")
async def export_customer_data(
    customer_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.OWNER))
) -> dict:
    """Art. 15 access request — a portable bundle of everything held about the customer."""
    customer = await _load_customer(scope, customer_id)
    orders = await _customer_orders(scope, customer_id)

    items_by_order: dict[uuid.UUID, list[dict]] = {}
    if orders:
        for item in await scope.session.scalars(
            select(OrderItem).where(OrderItem.order_id.in_([o.id for o in orders]))
        ):
            items_by_order.setdefault(item.order_id, []).append(
                {"name": item.name_snapshot, "quantity": item.quantity, "total_minor": item.total_minor}
            )

    conversations = list(
        await scope.session.scalars(
            select(Conversation).where(
                Conversation.restaurant_id == _rid(scope), Conversation.customer_id == customer_id
            )
        )
    )
    conversation_payloads = []
    for conversation in conversations:
        turns = await scope.session.scalars(
            select(ConversationTurn)
            .where(ConversationTurn.conversation_id == conversation.id)
            .order_by(ConversationTurn.seq)
        )
        conversation_payloads.append(
            {
                "id": str(conversation.id),
                "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
                "channel": conversation.channel.value,
                "turns": [{"role": t.role.value, "content": t.content} for t in turns],
            }
        )

    return build_export(
        customer={
            "id": str(customer.id), "phone_e164": customer.phone_e164, "name": customer.name,
            "language": customer.language, "addresses": customer.addresses,
            "preferences": customer.preferences, "consent": customer.consent,
            "created_at": customer.created_at.isoformat(),
        },
        orders=[
            {
                "id": str(o.id), "created_at": o.created_at.isoformat(), "subtotal_minor": o.subtotal_minor,
                "discount_minor": o.discount_minor, "delivery_fee_minor": o.delivery_fee_minor,
                "total_minor": o.total_minor, "currency": o.currency, "status": o.status.value,
                "type": o.type.value, "channel": o.channel.value, "address": o.address,
                "items": items_by_order.get(o.id, []),
            }
            for o in orders
        ],
        conversations=conversation_payloads,
        generated_at=datetime.now(UTC),
    )


@router.post("/customers/{customer_id}/erase", response_model=ErasureResultOut)
async def erase_customer_data(
    customer_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.OWNER))
) -> ErasureResultOut:
    """Art. 17 erasure — identity destroyed, financial records preserved."""
    customer = await _load_customer(scope, customer_id)
    orders = await _customer_orders(scope, customer_id)
    conversations = list(
        await scope.session.scalars(
            select(Conversation).where(
                Conversation.restaurant_id == _rid(scope), Conversation.customer_id == customer_id
            )
        )
    )
    turns: list[ConversationTurn] = []
    for conversation in conversations:
        turns.extend(
            await scope.session.scalars(
                select(ConversationTurn).where(ConversationTurn.conversation_id == conversation.id)
            )
        )

    plan = erase_customer(
        customer={"id": str(customer.id), "phone_e164": customer.phone_e164},
        orders=[{"id": str(o.id)} for o in orders],
        turns=[{"content": t.content} for t in turns],
        salt=get_settings().jwt_secret,
        now=datetime.now(UTC),
    )

    # Apply: identity fields cleared, order PII stripped, transcript content redacted.
    customer.phone_e164 = None
    customer.name = "Deleted customer"
    customer.addresses = []
    customer.preferences = {}
    customer.consent = {}
    customer.anonymized_at = plan.customer["anonymized_at"]

    for order in orders:
        order.address = None
        order.note = None
    for turn in turns:
        if turn.role in {TurnRole.CUSTOMER, TurnRole.AGENT}:
            turn.content = f"[erased:{len(turn.content or '')}]"
            turn.audio_object_key = None

    return ErasureResultOut(
        customer_id=customer.id,
        orders_stripped=len(orders),
        turns_redacted=len(turns),
        anonymized_at=customer.anonymized_at,
    )
