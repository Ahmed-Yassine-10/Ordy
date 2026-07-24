"""Outbound webhook envelope, HMAC signing, and retry policy (doc 07 §5).

Signature covers `timestamp.body` so a captured payload can't be replayed later with a
fresh timestamp. Verification is constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

SIGNATURE_TOLERANCE_SECONDS = 300
# 1m → 5m → 30m → 2h → 6h, then dead-letter (doc 07 §5).
RETRY_SCHEDULE_SECONDS = (60, 300, 1_800, 7_200, 21_600)

EVENT_TYPES = (
    "order.created",
    "order.confirmed",
    "order.status_changed",
    "order.cancelled",
    "reservation.created",
    "reservation.updated",
    "reservation.cancelled",
    "conversation.completed",
    "conversation.handoff_requested",
    "knowledge.change_pending_review",
    "workflow.degraded",
    "usage.threshold_reached",
)


@dataclass(slots=True)
class SignedPayload:
    body: str
    timestamp: int
    signature: str

    def headers(self, event_type: str, delivery_id: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Ordy-Event": event_type,
            "Ordy-Delivery": delivery_id,
            "Ordy-Timestamp": str(self.timestamp),
            "Ordy-Signature": self.signature,
        }


def build_envelope(
    *, event_id: str, event_type: str, restaurant_id: str, created_at: str, data: dict
) -> dict:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type '{event_type}'")
    return {
        "id": event_id,
        "type": event_type,
        "created_at": created_at,
        "restaurant_id": restaurant_id,
        "data": data,
    }


def _compute(secret: bytes, timestamp: int, body: str) -> str:
    digest = hmac.new(secret, f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"v1={digest}"


def sign(secret: bytes, envelope: dict, *, timestamp: int) -> SignedPayload:
    body = json.dumps(envelope, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return SignedPayload(body=body, timestamp=timestamp, signature=_compute(secret, timestamp, body))


def verify(
    secret: bytes, *, body: str, signature: str, timestamp: int, now: int,
    tolerance: int = SIGNATURE_TOLERANCE_SECONDS,
) -> bool:
    if abs(now - timestamp) > tolerance:
        return False
    return hmac.compare_digest(_compute(secret, timestamp, body), signature)


def next_retry_delay(attempt: int) -> int | None:
    """Delay before attempt N+1 (0-indexed); None once the schedule is exhausted."""
    if attempt < 0 or attempt >= len(RETRY_SCHEDULE_SECONDS):
        return None
    return RETRY_SCHEDULE_SECONDS[attempt]
