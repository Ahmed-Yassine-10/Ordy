"""Everything the engine needs to run the action gate for one turn.

The caller (API) resolves the PolicyContext from the database — tool bindings, menu
snapshot, hours, delivery policy, caps. The model never supplies any of it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ordy_tools.catalog import PLATFORM_TOOLS
from ordy_tools.executor import ExecutorAdapter, NativeAdapter
from ordy_tools.models import ToolSpec
from ordy_tools.policy import PolicyContext


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ToolRuntime:
    context: PolicyContext
    executor: ExecutorAdapter = field(default_factory=NativeAdapter)
    catalog: dict[str, ToolSpec] = field(default_factory=lambda: dict(PLATFORM_TOOLS))
    now: Callable[[], datetime] = _utcnow
    # Records every action attempt (validated/rejected/executed) for the audit trail.
    audit: list[dict] = field(default_factory=list)
