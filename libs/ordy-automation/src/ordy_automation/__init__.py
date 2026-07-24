"""ordy-automation — AI-generated, human-verified, deterministically-replayed browser
workflows for restaurants whose only interface is their website (doc 04 §6, ADR-011).

The safety guards (egress allowlist, payment-field refusal, selector sanitization) and
the replay logic are pure, so they are provable without a browser.
"""

from ordy_automation.compile import compile_trace
from ordy_automation.drift import (
    WorkflowHealth,
    notification_for,
    record_failure,
    record_success,
    record_verification,
)
from ordy_automation.models import RunResult, Step, StepResult, WorkflowDefinition
from ordy_automation.params import MissingParameter, bind_step, slots_in
from ordy_automation.runner import BrowserDriver, run_workflow
from ordy_automation.safety import (
    EgressBlocked,
    PaymentFieldRefused,
    assert_fields_safe,
    is_egress_allowed,
    is_never_fill,
    mask_for_artifact,
    sanitize_for_selector,
)

__all__ = [
    "BrowserDriver",
    "EgressBlocked",
    "MissingParameter",
    "PaymentFieldRefused",
    "RunResult",
    "Step",
    "StepResult",
    "WorkflowDefinition",
    "WorkflowHealth",
    "assert_fields_safe",
    "bind_step",
    "compile_trace",
    "is_egress_allowed",
    "is_never_fill",
    "mask_for_artifact",
    "notification_for",
    "record_failure",
    "record_success",
    "record_verification",
    "run_workflow",
    "sanitize_for_selector",
    "slots_in",
]
