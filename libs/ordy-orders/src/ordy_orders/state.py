"""Order + reservation state machines (doc 06 §3.3).

Transitions are explicit and enforced: staff UIs, the agent, and API clients all go
through the same rules, so an order can never jump from `draft` to `completed` or move
out of a terminal state.
"""

from __future__ import annotations

from ordy_core.enums import OrderStatus as OS
from ordy_core.enums import ReservationStatus as RS

ORDER_TRANSITIONS: dict[OS, set[OS]] = {
    OS.DRAFT: {OS.PENDING_CONFIRMATION, OS.CONFIRMED, OS.CANCELLED, OS.FAILED},
    OS.PENDING_CONFIRMATION: {OS.CONFIRMED, OS.CANCELLED, OS.FAILED},
    OS.CONFIRMED: {OS.PREPARING, OS.CANCELLED},
    OS.PREPARING: {OS.READY, OS.CANCELLED},
    OS.READY: {OS.OUT_FOR_DELIVERY, OS.COMPLETED, OS.CANCELLED},
    OS.OUT_FOR_DELIVERY: {OS.COMPLETED, OS.FAILED},
    OS.COMPLETED: set(),
    OS.CANCELLED: set(),
    OS.FAILED: set(),
}

RESERVATION_TRANSITIONS: dict[RS, set[RS]] = {
    RS.PENDING_CONFIRMATION: {RS.CONFIRMED, RS.CANCELLED},
    RS.CONFIRMED: {RS.SEATED, RS.CANCELLED, RS.NO_SHOW},
    RS.SEATED: {RS.COMPLETED},
    RS.COMPLETED: set(),
    RS.CANCELLED: set(),
    RS.NO_SHOW: set(),
}


class InvalidTransition(ValueError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move from '{current}' to '{target}'")
        self.current = current
        self.target = target


def can_transition(current: OS, target: OS) -> bool:
    return target in ORDER_TRANSITIONS.get(current, set())


def assert_transition(current: OS, target: OS) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current.value, target.value)


def is_terminal(status: OS) -> bool:
    return not ORDER_TRANSITIONS.get(status, set())


def can_transition_reservation(current: RS, target: RS) -> bool:
    return target in RESERVATION_TRANSITIONS.get(current, set())


def assert_reservation_transition(current: RS, target: RS) -> None:
    if not can_transition_reservation(current, target):
        raise InvalidTransition(current.value, target.value)


def next_states(current: OS) -> list[OS]:
    """What staff may do next — drives the dashboard's action buttons."""
    return sorted(ORDER_TRANSITIONS.get(current, set()), key=lambda s: s.value)
