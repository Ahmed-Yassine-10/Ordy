"""Action-gate data structures (doc 03 §4) + the stable error-code catalog (doc 07 §7).

Error codes are what the Conversation agent receives on rejection, so it can repair the
dialogue gracefully instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Single source of truth for both the gate and the DB column (doc 06 §3.6).
from ordy_core.enums import ActionStatus, RiskLevel

# ---- stable rejection codes (doc 07 §7) ----
TOOL_NOT_ENABLED = "TOOL_NOT_ENABLED"
CHANNEL_NOT_ALLOWED = "CHANNEL_NOT_ALLOWED"
SCHEMA_INVALID = "SCHEMA_INVALID"
PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
PRODUCT_UNAVAILABLE = "PRODUCT_UNAVAILABLE"
VARIANT_REQUIRED = "VARIANT_REQUIRED"
OUTSIDE_OPERATING_HOURS = "OUTSIDE_OPERATING_HOURS"
OUTSIDE_DELIVERY_ZONE = "OUTSIDE_DELIVERY_ZONE"
ORDER_BELOW_DELIVERY_MINIMUM = "ORDER_BELOW_DELIVERY_MINIMUM"
ORDER_ABOVE_CAP = "ORDER_ABOVE_CAP"
QUANTITY_ABOVE_CAP = "QUANTITY_ABOVE_CAP"
TOO_MANY_ITEMS = "TOO_MANY_ITEMS"
ACTION_BUDGET_EXCEEDED = "ACTION_BUDGET_EXCEEDED"
CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
CONFIRMATION_MISSING = "CONFIRMATION_MISSING"
ADAPTER_UNAVAILABLE = "ADAPTER_UNAVAILABLE"


__all_status__ = ActionStatus  # re-exported for callers importing from this module


@dataclass(slots=True)
class ToolSpec:
    """The ONLY interface the model ever sees for a capability (doc 03 §4.1)."""

    key: str
    version: int
    title: str
    description: str
    risk: RiskLevel
    requires_confirmation: bool
    idempotent: bool
    input_schema: dict
    output_schema: dict
    validators: list[str] = field(default_factory=list)
    compensation: dict | None = None

    def manifest_entry(self) -> dict:
        """What gets injected as a model function definition — schema only, no internals."""
        return {"name": self.key, "description": self.description, "parameters": self.input_schema}


@dataclass(slots=True)
class PlanStep:
    tool: str
    args: dict
    reason: str = ""
    depends_on: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ActionPlan:
    steps: list[PlanStep] = field(default_factory=list)
    plan_id: str = ""


@dataclass(slots=True)
class CheckResult:
    name: str
    passed: bool
    code: str | None = None
    message: str | None = None
    data: dict = field(default_factory=dict)


@dataclass(slots=True)
class ValidationReport:
    """Stored verbatim on the action record — the gate is self-documenting."""

    checks: list[CheckResult] = field(default_factory=list)
    passed: bool = False
    rejection_code: str | None = None
    human_message: str | None = None
    requires_confirmation: bool = False
    total_minor: int | None = None
    currency: str | None = None
    summary: str | None = None  # system-generated confirmation text, spoken verbatim
    priced_items: list[dict] = field(default_factory=list)

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "rejection_code": self.rejection_code,
            "human_message": self.human_message,
            "requires_confirmation": self.requires_confirmation,
            "total_minor": self.total_minor,
            "currency": self.currency,
            "summary": self.summary,
            "checks": [
                {"name": c.name, "passed": c.passed, "code": c.code, "message": c.message}
                for c in self.checks
            ],
        }


@dataclass(slots=True)
class ActionOutcome:
    status: ActionStatus
    output: dict | None = None
    error: dict | None = None
    external_ref: str | None = None
    adapter: str | None = None
    executed_at: datetime | None = None
