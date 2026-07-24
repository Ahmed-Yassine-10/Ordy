"""Data Subject Requests — export and erasure (doc 08 §7, GDPR Arts. 15 & 17).

Erasure **anonymizes rather than deletes**: the customer's identity is destroyed while
financial and audit records keep their integrity (totals, timestamps, tax trail). That is
both the lawful and the operationally correct outcome — a restaurant's accounts must not
develop holes because a customer exercised their rights.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

# Customer columns that carry identity and must be cleared.
IDENTITY_FIELDS = ("phone_e164", "name", "addresses", "preferences", "consent")
# Order columns that must SURVIVE erasure so the books still balance.
FINANCIAL_FIELDS = (
    "id", "created_at", "subtotal_minor", "discount_minor", "delivery_fee_minor",
    "total_minor", "currency", "status", "type",
)


@dataclass(slots=True)
class ErasureResult:
    customer: dict
    orders: list[dict]
    turns_redacted: int
    objects_deleted: list[str] = field(default_factory=list)


def pseudonymize(value: str, *, salt: str) -> str:
    """Stable, non-reversible pseudonym — lets us detect repeat requests without keeping
    the identifier."""
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:16]


def build_export(
    *, customer: dict, orders: list[dict], conversations: list[dict], generated_at: datetime
) -> dict:
    """Portable bundle for an Art. 15 access request."""
    return {
        "generated_at": generated_at.isoformat(),
        "format": "ordy.dsr.export/1",
        "customer": {
            key: customer.get(key)
            for key in ("id", "phone_e164", "name", "language", "addresses", "preferences", "consent", "created_at")
        },
        "orders": [
            {key: order.get(key) for key in (*FINANCIAL_FIELDS, "items", "address", "channel")}
            for order in orders
        ],
        "conversations": [
            {
                "id": conversation.get("id"),
                "started_at": conversation.get("started_at"),
                "channel": conversation.get("channel"),
                "turns": conversation.get("turns", []),
            }
            for conversation in conversations
        ],
    }


def anonymize_customer(customer: dict, *, salt: str, now: datetime) -> dict:
    """Destroy identity in place; keep the row so foreign keys and stats stay valid."""
    scrubbed = dict(customer)
    identifier = str(customer.get("phone_e164") or customer.get("id") or "")
    for field_name in IDENTITY_FIELDS:
        if field_name in {"addresses"}:
            scrubbed[field_name] = []
        elif field_name in {"preferences", "consent"}:
            scrubbed[field_name] = {}
        else:
            scrubbed[field_name] = None
    scrubbed["name"] = "Deleted customer"
    scrubbed["pseudonym"] = pseudonymize(identifier, salt=salt)
    scrubbed["anonymized_at"] = now
    return scrubbed


def strip_order_pii(order: dict) -> dict:
    """Keep the money, drop the person."""
    kept = {key: order.get(key) for key in FINANCIAL_FIELDS if key in order}
    kept["customer_id"] = order.get("customer_id")  # points at the anonymized row
    kept["address"] = None
    kept["note"] = None
    return kept


def redact_turn(content: str | None) -> str:
    """Transcripts may contain anything spoken — replace with a length-preserving marker
    so conversation analytics keep shape without keeping content."""
    if not content:
        return ""
    return f"[erased:{len(content)}]"


def erase_customer(
    *, customer: dict, orders: list[dict], turns: list[dict], salt: str, now: datetime,
    audio_object_keys: list[str] | None = None,
) -> ErasureResult:
    return ErasureResult(
        customer=anonymize_customer(customer, salt=salt, now=now),
        orders=[strip_order_pii(order) for order in orders],
        turns_redacted=len(turns),
        objects_deleted=list(audio_object_keys or []),
    )
