"""Delivery zone matching (doc 06 §3.2).

Two geometries: a circle (`center` + `radius_m`) and a GeoJSON-style polygon. Matching
picks the cheapest applicable zone, so overlapping zones behave predictably for the
customer rather than depending on row order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

EARTH_RADIUS_M = 6_371_000.0


@dataclass(slots=True)
class DeliveryZone:
    name: str
    fee_minor: int = 0
    min_order_minor: int = 0
    eta_minutes: int | None = None
    is_active: bool = True
    kind: str = "radius"  # radius | polygon
    center: tuple[float, float] | None = None  # (lat, lon)
    radius_m: float = 0.0
    polygon: list[tuple[float, float]] = field(default_factory=list)  # [(lat, lon), …]


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Ray casting. Polygon is a closed ring of (lat, lon); winding order doesn't matter."""
    if len(polygon) < 3:
        return False
    lat, lon = point
    inside = False
    for i in range(len(polygon)):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[i - 1]
        intersects = (lon_i > lon) != (lon_j > lon) and lat < (
            (lat_j - lat_i) * (lon - lon_i) / ((lon_j - lon_i) or 1e-12) + lat_i
        )
        if intersects:
            inside = not inside
    return inside


def zone_contains(zone: DeliveryZone, point: tuple[float, float]) -> bool:
    if not zone.is_active:
        return False
    if zone.kind == "polygon":
        return point_in_polygon(point, zone.polygon)
    if zone.center is None:
        return False
    return haversine_m(zone.center, point) <= zone.radius_m


def find_zone(zones: list[DeliveryZone], point: tuple[float, float]) -> DeliveryZone | None:
    """Cheapest matching active zone, or None when the address is out of area."""
    matches = [z for z in zones if zone_contains(z, point)]
    if not matches:
        return None
    return min(matches, key=lambda z: (z.fee_minor, z.min_order_minor))
