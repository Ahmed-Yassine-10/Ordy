"""Order domain tests: state machine, hours (incl. midnight spans), zones, totals."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from ordy_core.enums import OrderStatus as OS
from ordy_core.enums import ReservationStatus as RS
from ordy_orders.hours import HoursWindow, is_service_open, open_services
from ordy_orders.state import (
    InvalidTransition,
    assert_transition,
    can_transition,
    can_transition_reservation,
    is_terminal,
    next_states,
)
from ordy_orders.totals import apply_promotion, compute_totals
from ordy_orders.zones import DeliveryZone, find_zone, haversine_m, point_in_polygon

# ---------- state machine ----------


def test_happy_path_transitions() -> None:
    assert can_transition(OS.CONFIRMED, OS.PREPARING)
    assert can_transition(OS.PREPARING, OS.READY)
    assert can_transition(OS.READY, OS.COMPLETED)


def test_illegal_jumps_are_rejected() -> None:
    assert not can_transition(OS.DRAFT, OS.COMPLETED)
    assert not can_transition(OS.CONFIRMED, OS.READY)
    with pytest.raises(InvalidTransition):
        assert_transition(OS.COMPLETED, OS.PREPARING)


def test_terminal_states_are_final() -> None:
    for status in (OS.COMPLETED, OS.CANCELLED, OS.FAILED):
        assert is_terminal(status)
        assert next_states(status) == []


def test_reservation_transitions() -> None:
    assert can_transition_reservation(RS.CONFIRMED, RS.SEATED)
    assert can_transition_reservation(RS.CONFIRMED, RS.NO_SHOW)
    assert not can_transition_reservation(RS.COMPLETED, RS.SEATED)


# ---------- operating hours ----------

TZ = "Africa/Tunis"


def _windows() -> list[HoursWindow]:
    return [
        # Monday lunch 11:00–15:00
        HoursWindow("pickup", 0, time(11, 0), time(15, 0)),
        # Friday night 19:00 → 02:00 (spans midnight into Saturday)
        HoursWindow("pickup", 4, time(19, 0), time(2, 0)),
    ]


def test_open_inside_normal_window() -> None:
    at = datetime(2026, 7, 27, 11, 30, tzinfo=UTC)  # Monday 12:30 local (UTC+1)
    assert is_service_open(_windows(), service="pickup", at=at, timezone=TZ)


def test_closed_outside_window() -> None:
    at = datetime(2026, 7, 27, 16, 0, tzinfo=UTC)  # Monday 17:00 local
    assert not is_service_open(_windows(), service="pickup", at=at, timezone=TZ)


def test_midnight_spanning_window_stays_open_after_midnight() -> None:
    # Saturday 01:00 local belongs to Friday's 19:00→02:00 window.
    at = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)  # Sat 01:00 local
    assert is_service_open(_windows(), service="pickup", at=at, timezone=TZ)
    # …but 03:00 local Saturday is closed.
    assert not is_service_open(
        _windows(), service="pickup", at=datetime(2026, 8, 1, 2, 0, tzinfo=UTC), timezone=TZ
    )


def test_service_isolation_and_map_shape() -> None:
    at = datetime(2026, 7, 27, 11, 30, tzinfo=UTC)
    services = open_services(_windows(), at=at, timezone=TZ)
    assert services["pickup"] is True
    assert services["delivery"] is False  # no delivery windows defined
    assert set(services) == {"pickup", "delivery", "dine_in", "reservation"}


# ---------- delivery zones ----------

SFAX = (34.7406, 10.7603)


def test_radius_zone_matching() -> None:
    near = DeliveryZone(name="Centre", kind="radius", center=SFAX, radius_m=3000, fee_minor=2000)
    far_point = (34.80, 10.85)  # ~10 km away
    assert find_zone([near], SFAX) is near
    assert find_zone([near], far_point) is None


def test_polygon_zone_matching() -> None:
    square = DeliveryZone(
        name="Square", kind="polygon",
        polygon=[(34.70, 10.70), (34.80, 10.70), (34.80, 10.80), (34.70, 10.80)],
        fee_minor=1500,
    )
    assert find_zone([square], SFAX) is square
    assert find_zone([square], (34.90, 10.90)) is None
    assert point_in_polygon((34.75, 10.75), square.polygon)


def test_cheapest_overlapping_zone_wins() -> None:
    cheap = DeliveryZone(name="Cheap", kind="radius", center=SFAX, radius_m=5000, fee_minor=1000)
    pricey = DeliveryZone(name="Pricey", kind="radius", center=SFAX, radius_m=5000, fee_minor=4000)
    assert find_zone([pricey, cheap], SFAX) is cheap


def test_inactive_zone_never_matches() -> None:
    off = DeliveryZone(name="Off", kind="radius", center=SFAX, radius_m=9000, is_active=False)
    assert find_zone([off], SFAX) is None


def test_haversine_is_sane() -> None:
    assert 900 < haversine_m(SFAX, (34.7496, 10.7603)) < 1100  # ~1 km north


# ---------- totals + promotions ----------


def test_totals_add_delivery_fee() -> None:
    totals = compute_totals(32_000, delivery_fee_minor=2_500)
    assert totals.total_minor == 34_500


def test_percent_promotion_respects_minimum() -> None:
    rule = {"type": "percent", "value": 10, "conditions": {"min_order_minor": 30_000}}
    assert apply_promotion(32_000, rule) == 3_200
    assert apply_promotion(20_000, rule) == 0  # under the minimum


def test_discount_never_exceeds_subtotal_or_goes_negative() -> None:
    """An injected/oversized discount can't produce a negative or free order."""
    assert apply_promotion(10_000, {"type": "amount", "value": 999_999}) == 10_000
    totals = compute_totals(10_000, delivery_fee_minor=2_000, promotion={"type": "percent", "value": 500})
    assert totals.discount_minor == 10_000  # percent clamped to 100
    assert totals.total_minor == 2_000  # fee still owed; never below zero


def test_unknown_promotion_rule_discounts_nothing() -> None:
    assert apply_promotion(10_000, {"type": "free_everything"}) == 0
    assert apply_promotion(10_000, None) == 0
