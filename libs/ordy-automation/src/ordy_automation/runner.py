"""Deterministic workflow replay (doc 04 §6 step 4).

No LLM in this loop. Every step is executed exactly as approved, each assertion must
hold, and any failure aborts the run with artifacts captured — a partially-applied order
is never left behind silently. Playwright implements ``BrowserDriver`` in the sandbox
service; tests drive a fake.
"""

from __future__ import annotations

from typing import Protocol

from ordy_automation.models import WRITE_OPS, RunResult, Step, StepResult, WorkflowDefinition
from ordy_automation.params import MissingParameter, bind_step
from ordy_automation.safety import (
    EgressBlocked,
    PaymentFieldRefused,
    assert_egress_allowed,
    assert_fields_safe,
)


class BrowserDriver(Protocol):
    async def goto(self, url: str) -> None: ...
    async def click(self, selectors: list[str]) -> bool: ...
    async def select_option(self, target: str, value: str) -> bool: ...
    async def fill(self, field: str, value: str) -> None: ...
    async def check(self, expectation: str) -> bool: ...
    async def capture(self, name: str) -> str: ...
    async def read(self, name: str) -> str | None: ...


async def run_workflow(
    workflow: WorkflowDefinition,
    params: dict[str, str],
    driver: BrowserDriver,
    *,
    allowlist: set[str] | None = None,
    platform_confirmed: bool = False,
    dry_run: bool = False,
) -> RunResult:
    """Replay a verified workflow. ``dry_run`` stops before any irreversible submit."""
    allowed = allowlist or {workflow.target_domain}
    result = RunResult(ok=True)

    for index, raw_step in enumerate(workflow.steps):
        try:
            step = bind_step(raw_step, params)
        except MissingParameter as exc:
            return _abort(result, index, raw_step.op, "MISSING_PARAMETER", f"no value for '{exc.args[0]}'")

        # A verification dry-run stops before anything irreversible — checked first, since
        # a dry run legitimately has no confirmed action behind it.
        if dry_run and step.op == "confirm_order":
            result.steps.append(StepResult(index, step.op, True, "skipped (dry run)"))
            break
        # A step that submits an order requires the platform's confirmed action — the
        # browser layer can never place an order the action gate didn't approve.
        if step.requires == "platform_confirmed_action" and not platform_confirmed:
            return _abort(result, index, step.op, "CONFIRMATION_MISSING", "submit without a confirmed action")

        try:
            detail = await _execute(step, driver, allowed)
        except EgressBlocked as exc:
            return _abort(result, index, step.op, "EGRESS_BLOCKED", str(exc), driver)
        except PaymentFieldRefused as exc:
            return _abort(result, index, step.op, "PAYMENT_FIELD_REFUSED", str(exc), driver)
        except Exception as exc:  # noqa: BLE001 — any driver error aborts the run
            return _abort(result, index, step.op, "STEP_FAILED", f"{type(exc).__name__}: {exc}", driver)

        if detail is False:
            return _abort(result, index, step.op, "SELECTOR_FAILED", "target not found (site may have changed)", driver)

        if step.expect and not await driver.check(step.expect):
            return _abort(result, index, step.op, "ASSERTION_FAILED", f"expected '{step.expect}'", driver)

        if step.capture:
            captured = await driver.read(step.capture)
            if captured is not None:
                result.captured[step.capture] = captured

        result.steps.append(StepResult(index, step.op, True))

    return result


async def _execute(step: Step, driver: BrowserDriver, allowed: set[str]) -> bool | None:
    if step.op in WRITE_OPS:
        assert_fields_safe(step.fields, step.never_fill)

    if step.op == "goto":
        assert_egress_allowed(step.url or "", allowed)
        await driver.goto(step.url or "")
        return None
    if step.op in {"click", "search_click", "goto_cart_checkout", "confirm_order"}:
        return await driver.click(step.strategy or ([step.target] if step.target else []))
    if step.op == "select_option":
        return await driver.select_option(step.target or "", step.value or "")
    if step.op == "fill_form":
        for name, value in step.fields.items():
            await driver.fill(name, value)
        return None
    raise ValueError(f"unknown workflow op '{step.op}'")


def _abort(
    result: RunResult, index: int, op: str, code: str, message: str, driver: BrowserDriver | None = None
) -> RunResult:
    result.ok = False
    result.error_code = code
    result.error_message = message
    result.steps.append(StepResult(index=index, op=op, ok=False, detail=message))
    return result
