"""Operating hours evaluation (doc 06 §3.2).

Windows are stored in the restaurant's LOCAL time with `day_of_week` 0=Monday. A window
whose `closes` is earlier than its `opens` spans midnight (e.g. 19:00→02:00) and stays
open into the following day — the case naive implementations get wrong, and exactly the
case a late-night restaurant lives in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(slots=True)
class HoursWindow:
    service: str  # pickup | delivery | dine_in | reservation
    day_of_week: int  # 0=Mon … 6=Sun (local)
    opens: time
    closes: time

    @property
    def spans_midnight(self) -> bool:
        return self.closes <= self.opens


def is_service_open(
    windows: list[HoursWindow], *, service: str, at: datetime, timezone: str = "Africa/Tunis"
) -> bool:
    """True if `service` is open at instant `at` (any tz) for this restaurant."""
    local = at.astimezone(ZoneInfo(timezone))
    today = local.weekday()
    yesterday = (today - 1) % 7
    now = local.time()

    for window in windows:
        if window.service != service:
            continue
        if not window.spans_midnight:
            if window.day_of_week == today and window.opens <= now < window.closes:
                return True
        else:
            # Opened today and still running before midnight…
            if window.day_of_week == today and now >= window.opens:
                return True
            # …or opened yesterday and still running after midnight.
            if window.day_of_week == yesterday and now < window.closes:
                return True
    return False


def open_services(
    windows: list[HoursWindow], *, at: datetime, timezone: str = "Africa/Tunis"
) -> dict[str, bool]:
    """Service→open map, the shape the policy engine's PolicyContext expects."""
    return {
        service: is_service_open(windows, service=service, at=at, timezone=timezone)
        for service in ("pickup", "delivery", "dine_in", "reservation")
    }
