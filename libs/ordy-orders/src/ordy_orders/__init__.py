"""ordy-orders — the order domain: status machines, hours, delivery zones, totals.

Pure and dependency-free, so the rules that decide whether a restaurant is open, whether
an address is deliverable, and what an order costs are unit-testable without a database.
"""

from ordy_orders.hours import HoursWindow, is_service_open, open_services
from ordy_orders.state import (
    InvalidTransition,
    assert_reservation_transition,
    assert_transition,
    can_transition,
    can_transition_reservation,
    is_terminal,
    next_states,
)
from ordy_orders.totals import OrderTotals, apply_promotion, compute_totals
from ordy_orders.zones import DeliveryZone, find_zone, haversine_m, point_in_polygon, zone_contains

__all__ = [
    "DeliveryZone",
    "HoursWindow",
    "InvalidTransition",
    "OrderTotals",
    "apply_promotion",
    "assert_reservation_transition",
    "assert_transition",
    "can_transition",
    "can_transition_reservation",
    "compute_totals",
    "find_zone",
    "haversine_m",
    "is_service_open",
    "is_terminal",
    "next_states",
    "open_services",
    "point_in_polygon",
    "zone_contains",
]
