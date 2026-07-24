"""Selector-drift tracking and the degrade chain (doc 04 §5, ADR-011).

Sites change. When a workflow's selectors stop matching, the tool must degrade *loudly*
and fall back to Ordy's own store rather than silently failing orders:

    active → (failure) → degraded → (repeat failures) → disabled → fallback to native

Recovery is not automatic on a single success — a verification run must pass.
"""

from __future__ import annotations

from dataclasses import dataclass

from ordy_core.enums import WorkflowStatus

DISABLE_AFTER_FAILURES = 3


@dataclass(slots=True)
class WorkflowHealth:
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    failure_count: int = 0

    @property
    def usable(self) -> bool:
        """Only a verified/active workflow may run live traffic."""
        return self.status in {WorkflowStatus.ACTIVE, WorkflowStatus.VERIFIED}

    @property
    def should_fallback(self) -> bool:
        return not self.usable


def record_failure(health: WorkflowHealth) -> WorkflowHealth:
    """One live failure degrades immediately; repeats disable the workflow."""
    count = health.failure_count + 1
    status = WorkflowStatus.DISABLED if count >= DISABLE_AFTER_FAILURES else WorkflowStatus.DEGRADED
    return WorkflowHealth(status=status, failure_count=count)


def record_success(health: WorkflowHealth) -> WorkflowHealth:
    """A live success clears the counter but never re-enables a disabled workflow."""
    if health.status is WorkflowStatus.DISABLED:
        return health
    return WorkflowHealth(status=WorkflowStatus.ACTIVE, failure_count=0)


def record_verification(health: WorkflowHealth, *, passed: bool) -> WorkflowHealth:
    """A verification dry-run is the ONLY way back from disabled."""
    if passed:
        return WorkflowHealth(status=WorkflowStatus.VERIFIED, failure_count=0)
    return WorkflowHealth(status=WorkflowStatus.DISABLED, failure_count=health.failure_count)


def notification_for(health: WorkflowHealth, action_key: str) -> str | None:
    if health.status is WorkflowStatus.DEGRADED:
        return f"'{action_key}' automation failed — falling back to Ordy orders while we re-check the site."
    if health.status is WorkflowStatus.DISABLED:
        return f"'{action_key}' automation is disabled after repeated failures — orders are going to Ordy directly."
    return None
