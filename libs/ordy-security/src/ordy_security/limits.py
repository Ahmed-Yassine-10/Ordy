"""Rate limiting + cost circuit breakers (doc 08 §8).

Layered budgets, all enforced in code: per customer, per tenant, per platform. The cost
breaker is an agent platform's fuse box — a runaway loop or an abuse campaign burns real
vendor money, so spend is capped and the system degrades to safe static responses rather
than billing its way through an incident.

Both take an injected clock so they are deterministic under test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(slots=True)
class TokenBucket:
    """Classic token bucket. `capacity` burst, `refill_per_second` sustained rate.

    ``updated_at`` is None-until-first-use rather than 0.0: a monotonic clock legitimately
    starts at zero, and a falsy check there would stop the bucket ever refilling.
    """

    capacity: float
    refill_per_second: float
    tokens: float | None = None
    updated_at: float | None = None

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = self.capacity

    def allow(self, now: float, cost: float = 1.0) -> bool:
        assert self.tokens is not None
        if self.updated_at is not None:
            elapsed = max(0.0, now - self.updated_at)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.updated_at = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def retry_after(self, cost: float = 1.0) -> float:
        deficit = max(0.0, cost - (self.tokens or 0.0))
        return deficit / self.refill_per_second if self.refill_per_second else float("inf")


class RateLimiter:
    """Keyed buckets — `t:{restaurant}:{scope}` in Redis in production."""

    def __init__(self, capacity: float, refill_per_second: float) -> None:
        self._capacity = capacity
        self._refill = refill_per_second
        self._buckets: dict[str, TokenBucket] = {}

    def allow(self, key: str, now: float, cost: float = 1.0) -> bool:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(capacity=self._capacity, refill_per_second=self._refill, updated_at=now)
            self._buckets[key] = bucket
        return bucket.allow(now, cost)

    def retry_after(self, key: str, cost: float = 1.0) -> float:
        bucket = self._buckets.get(key)
        return bucket.retry_after(cost) if bucket else 0.0


class BreakerState(StrEnum):
    CLOSED = "closed"  # normal
    OPEN = "open"  # tripped — degrade to safe responses
    HALF_OPEN = "half_open"  # probing recovery


@dataclass(slots=True)
class CostBreaker:
    """Trips when vendor spend in a rolling window exceeds the budget (doc 08 §8)."""

    budget_minor: int
    window_seconds: float = 3600.0
    cooldown_seconds: float = 900.0
    _events: list[tuple[float, int]] = field(default_factory=list)
    state: BreakerState = BreakerState.CLOSED
    opened_at: float | None = None

    def record(self, now: float, cost_minor: int) -> BreakerState:
        self._events.append((now, cost_minor))
        self._prune(now)
        if self.state is BreakerState.CLOSED and self.spend(now) > self.budget_minor:
            self.state = BreakerState.OPEN
            self.opened_at = now
        return self.state

    def spend(self, now: float) -> int:
        self._prune(now)
        return sum(cost for _, cost in self._events)

    def allow(self, now: float) -> bool:
        """False while tripped; after the cooldown we probe with half-open."""
        if self.state is BreakerState.OPEN and self.opened_at is not None:
            if now - self.opened_at >= self.cooldown_seconds:
                self.state = BreakerState.HALF_OPEN
                return True
            return False
        return True

    def reset(self) -> None:
        self.state = BreakerState.CLOSED
        self.opened_at = None
        self._events.clear()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self._events = [(at, cost) for at, cost in self._events if at >= cutoff]
