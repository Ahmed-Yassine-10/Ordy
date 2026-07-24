"""Customer-confirmation gate (doc 03 §3.4 step 6).

A state-changing action needs an EXPLICIT, RECENT confirmation of a system-generated
summary. Two independent staleness guards: wall-clock TTL and conversational distance
(a "yes" three turns later is not consent to the thing proposed earlier).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

DEFAULT_TTL_SECONDS = 120
DEFAULT_MAX_TURN_GAP = 2


class ConfirmationState(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    EXPIRED = "expired"


@dataclass(slots=True)
class ConfirmationRequest:
    action_id: str
    tool_key: str
    summary: str
    args: dict
    created_at: datetime
    expires_at: datetime
    turn_seq: int
    state: ConfirmationState = ConfirmationState.PENDING

    def as_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "tool_key": self.tool_key,
            "summary": self.summary,
            "args": self.args,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "turn_seq": self.turn_seq,
            "state": self.state.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConfirmationRequest":
        return cls(
            action_id=data["action_id"],
            tool_key=data["tool_key"],
            summary=data["summary"],
            args=data.get("args", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            turn_seq=int(data.get("turn_seq", 0)),
            state=ConfirmationState(data.get("state", "pending")),
        )


def request_confirmation(
    *, action_id: str, tool_key: str, summary: str, args: dict, now: datetime,
    turn_seq: int, ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> ConfirmationRequest:
    return ConfirmationRequest(
        action_id=action_id, tool_key=tool_key, summary=summary, args=args,
        created_at=now, expires_at=now + timedelta(seconds=ttl_seconds), turn_seq=turn_seq,
    )


def resolve_confirmation(
    request: ConfirmationRequest, *, approved: bool, now: datetime, current_turn_seq: int,
    max_turn_gap: int = DEFAULT_MAX_TURN_GAP,
) -> ConfirmationState:
    """Consent is only valid if fresh in BOTH time and conversational distance."""
    if request.state is not ConfirmationState.PENDING:
        return request.state
    if now > request.expires_at or (current_turn_seq - request.turn_seq) > max_turn_gap:
        request.state = ConfirmationState.EXPIRED
        return request.state
    request.state = ConfirmationState.CONFIRMED if approved else ConfirmationState.DECLINED
    return request.state


_AFFIRMATIVE = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go ahead", "confirm", "place it",
    "oui", "d'accord", "vas-y", "confirme", "ايه", "أيه", "نعم", "برافو", "baheh", "bahi",
}
_NEGATIVE = {"no", "nope", "cancel", "stop", "wait", "non", "annule", "لا", "لأ"}


def interpret_response(text: str) -> bool | None:
    """Map an utterance to approve/decline/unclear. Anything unclear is NOT consent."""
    t = " ".join((text or "").lower().split())
    if not t:
        return None
    if any(t == n or t.startswith(f"{n} ") for n in _NEGATIVE):
        return False
    if any(t == a or t.startswith(f"{a} ") or t.endswith(f" {a}") for a in _AFFIRMATIVE):
        return True
    return None
