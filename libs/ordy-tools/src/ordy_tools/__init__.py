"""ordy-tools — the action gate (doc 03 §4, doc 08 §6.2).

The LLM's only power is proposing a tool call. Everything between that proposal and a
real side effect lives here, in deterministic code: whitelist → schema → referential
integrity + server-side pricing → business rules → caps → confirmation → idempotent
execution → outcome validation.
"""

from ordy_tools.catalog import PLATFORM_TOOLS, get_tool, manifest
from ordy_tools.confirm import (
    ConfirmationRequest,
    ConfirmationState,
    interpret_response,
    request_confirmation,
    resolve_confirmation,
)
from ordy_tools.executor import ExecutorAdapter, NativeAdapter, execute_action
from ordy_tools.models import (
    ActionOutcome,
    ActionPlan,
    ActionStatus,
    CheckResult,
    PlanStep,
    ToolSpec,
    ValidationReport,
)
from ordy_tools.policy import (
    Caps,
    DeliveryPolicy,
    PolicyContext,
    ToolBinding,
    build_summary,
    validate_action,
)
from ordy_tools.pricing import PricedItem, ProductSnapshot, VariantSnapshot, format_money, price_items

__all__ = [
    "PLATFORM_TOOLS",
    "ActionOutcome",
    "ActionPlan",
    "ActionStatus",
    "Caps",
    "CheckResult",
    "ConfirmationRequest",
    "ConfirmationState",
    "DeliveryPolicy",
    "ExecutorAdapter",
    "NativeAdapter",
    "PlanStep",
    "PolicyContext",
    "PricedItem",
    "ProductSnapshot",
    "ToolBinding",
    "ToolSpec",
    "ValidationReport",
    "VariantSnapshot",
    "build_summary",
    "execute_action",
    "format_money",
    "get_tool",
    "interpret_response",
    "manifest",
    "price_items",
    "request_confirmation",
    "resolve_confirmation",
    "validate_action",
]
