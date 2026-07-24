"""Automation safety + replay tests — the sandbox's security properties, proven without
a browser (the driver is faked). These mirror the Phase 8 exit criteria."""

from __future__ import annotations

import asyncio

from ordy_automation.compile import compile_trace
from ordy_automation.drift import (
    WorkflowHealth,
    notification_for,
    record_failure,
    record_success,
    record_verification,
)
from ordy_automation.models import Step, WorkflowDefinition
from ordy_automation.params import bind_step
from ordy_automation.runner import run_workflow
from ordy_automation.safety import (
    is_egress_allowed,
    is_never_fill,
    mask_for_artifact,
    sanitize_for_selector,
)
from ordy_core.enums import WorkflowStatus

DOMAIN = "pizzarustica.tn"


# ---------- fake browser ----------


class FakeBrowser:
    def __init__(self, *, fail_selector: str | None = None, fail_check: str | None = None) -> None:
        self.visited: list[str] = []
        self.filled: dict[str, str] = {}
        self.clicked: list[str] = []
        self._fail_selector = fail_selector
        self._fail_check = fail_check

    async def goto(self, url: str) -> None:
        self.visited.append(url)

    async def click(self, selectors: list[str]) -> bool:
        for selector in selectors:
            if self._fail_selector and self._fail_selector in selector:
                return False
            self.clicked.append(selector)
            return True
        return False

    async def select_option(self, target: str, value: str) -> bool:
        self.clicked.append(f"{target}={value}")
        return True

    async def fill(self, field: str, value: str) -> None:
        self.filled[field] = value

    async def check(self, expectation: str) -> bool:
        return expectation != self._fail_check

    async def capture(self, name: str) -> str:
        return f"s3://artifacts/{name}.png"

    async def read(self, name: str) -> str | None:
        return "ORD-1234" if name == "order_reference" else None


def _workflow(steps: list[Step] | None = None) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id="wf_1",
        action_key="create_order",
        target_domain=DOMAIN,
        steps=steps
        or [
            Step(op="goto", url=f"https://{DOMAIN}/menu"),
            Step(op="search_click", strategy=["css:[data-item='{product_query}']"], expect="item_page_or_modal"),
            Step(op="select_option", target="size", value="{variant_label}", expect="option_selected"),
            Step(op="click", strategy=["css:.add-to-cart"], expect="cart_count_increased"),
            Step(op="goto_cart_checkout", strategy=["css:.checkout"], expect="checkout_form_visible"),
            Step(op="fill_form", fields={"name": "{customer_name}", "phone": "{phone}"}, expect="form_filled"),
            Step(op="confirm_order", strategy=["css:.submit"], expect="order_confirmation_visible",
                 requires="platform_confirmed_action", capture="order_reference"),
        ],
    )


PARAMS = {
    "product_query": "Pizza Pepperoni",
    "variant_label": "Large",
    "customer_name": "Amine",
    "phone": "+21620000000",
}


# ---------- SSRF / egress allowlist ----------


def test_metadata_endpoint_is_blocked() -> None:
    assert not is_egress_allowed("http://169.254.169.254/latest/meta-data/", {DOMAIN})
    assert not is_egress_allowed("http://metadata.google.internal/", {DOMAIN})


def test_private_and_loopback_ranges_are_blocked() -> None:
    for url in (
        "http://127.0.0.1:8000/",
        "http://localhost/admin",
        "http://10.0.0.5/internal",
        "http://192.168.1.10/",
        "http://172.16.0.9/",
        "http://[::1]/",
    ):
        assert not is_egress_allowed(url, {DOMAIN}), url


def test_non_allowlisted_domain_and_bad_schemes_blocked() -> None:
    assert not is_egress_allowed("https://evil.example/steal", {DOMAIN})
    assert not is_egress_allowed("file:///etc/passwd", {DOMAIN})
    assert not is_egress_allowed("data:text/html,<script>", {DOMAIN})
    # A lookalike domain must not satisfy the suffix check.
    assert not is_egress_allowed(f"https://evil-{DOMAIN}.attacker.com/", {DOMAIN})


def test_target_domain_and_subdomains_allowed() -> None:
    assert is_egress_allowed(f"https://{DOMAIN}/menu", {DOMAIN})
    assert is_egress_allowed(f"https://www.{DOMAIN}/checkout", {DOMAIN})


def test_runner_aborts_on_disallowed_navigation() -> None:
    workflow = _workflow([Step(op="goto", url="http://169.254.169.254/latest/meta-data/")])
    result = asyncio.run(run_workflow(workflow, PARAMS, FakeBrowser(), allowlist={DOMAIN}))
    assert not result.ok and result.error_code == "EGRESS_BLOCKED"


# ---------- payment credentials are never typed ----------


def test_never_fill_matching() -> None:
    for field in ("card_number", "cardNumber", "cc-number", "CVV", "security_code", "password", "iban"):
        assert is_never_fill(field), field
    for field in ("name", "phone", "address_line1", "note"):
        assert not is_never_fill(field), field


def test_runner_refuses_payment_fields_even_if_workflow_asks() -> None:
    """A drifted or tampered workflow cannot smuggle card entry through."""
    workflow = _workflow([
        Step(op="fill_form", fields={"name": "{customer_name}", "card_number": "4111111111111111"}),
    ])
    browser = FakeBrowser()
    result = asyncio.run(run_workflow(workflow, PARAMS, browser, allowlist={DOMAIN}))
    assert not result.ok and result.error_code == "PAYMENT_FIELD_REFUSED"
    assert browser.filled == {}  # nothing typed at all — the whole step is refused


def test_artifacts_mask_sensitive_values() -> None:
    assert mask_for_artifact("card_number", "4111111111111111") == "***"
    assert mask_for_artifact("password", "hunter2") == "***"
    assert mask_for_artifact("phone", "+21620000000").endswith("00")


# ---------- parameters are data, not code ----------


def test_selector_injection_via_parameter_is_neutralized() -> None:
    """A crafted product name must not add structure to the selector it lands in:
    the bound selector keeps exactly the template's own quotes/brackets."""
    template = "css:[data-item='{product_query}']"
    step = Step(op="search_click", strategy=[template])
    bound = bind_step(step, {"product_query": "'] , [data-item='Admin"}).strategy[0]

    for char in ("'", "[", "]"):
        assert bound.count(char) == template.count(char), (char, bound)
    assert sanitize_for_selector("<script>alert(1)</script>") == "scriptalert1/script"


def test_missing_parameter_aborts_before_touching_the_browser() -> None:
    browser = FakeBrowser()
    result = asyncio.run(run_workflow(_workflow(), {"product_query": "Pizza"}, browser, allowlist={DOMAIN}))
    assert not result.ok and result.error_code == "MISSING_PARAMETER"


# ---------- confirmation coupling ----------


def test_submit_requires_a_platform_confirmed_action() -> None:
    browser = FakeBrowser()
    result = asyncio.run(run_workflow(_workflow(), PARAMS, browser, allowlist={DOMAIN}))
    assert not result.ok and result.error_code == "CONFIRMATION_MISSING"
    assert ".submit" not in browser.clicked  # the order was never placed


def test_confirmed_run_completes_and_captures_reference() -> None:
    browser = FakeBrowser()
    result = asyncio.run(
        run_workflow(_workflow(), PARAMS, browser, allowlist={DOMAIN}, platform_confirmed=True)
    )
    assert result.ok
    assert result.captured["order_reference"] == "ORD-1234"
    assert browser.filled["name"] == "Amine"


def test_dry_run_stops_before_submitting() -> None:
    browser = FakeBrowser()
    result = asyncio.run(run_workflow(_workflow(), PARAMS, browser, allowlist={DOMAIN}, dry_run=True))
    assert result.ok
    assert ".submit" not in browser.clicked  # verification never places a real order


# ---------- drift: broken selectors degrade loudly ----------


def test_broken_selector_aborts_the_run() -> None:
    browser = FakeBrowser(fail_selector="add-to-cart")
    result = asyncio.run(
        run_workflow(_workflow(), PARAMS, browser, allowlist={DOMAIN}, platform_confirmed=True)
    )
    assert not result.ok and result.error_code == "SELECTOR_FAILED"
    assert result.failed_step.op == "click"


def test_failed_assertion_aborts_the_run() -> None:
    browser = FakeBrowser(fail_check="cart_count_increased")
    result = asyncio.run(
        run_workflow(_workflow(), PARAMS, browser, allowlist={DOMAIN}, platform_confirmed=True)
    )
    assert not result.ok and result.error_code == "ASSERTION_FAILED"


def test_degrade_chain_disables_and_falls_back() -> None:
    health = WorkflowHealth(status=WorkflowStatus.ACTIVE)
    health = record_failure(health)
    assert health.status is WorkflowStatus.DEGRADED
    assert health.should_fallback  # orders route to native immediately
    assert "falling back" in notification_for(health, "create_order")

    health = record_failure(record_failure(health))
    assert health.status is WorkflowStatus.DISABLED
    assert "disabled" in notification_for(health, "create_order")

    # A live success cannot silently re-enable a disabled workflow…
    assert record_success(health).status is WorkflowStatus.DISABLED
    # …only a passing verification run can.
    assert record_verification(health, passed=True).status is WorkflowStatus.VERIFIED


# ---------- compilation ----------


def test_compile_trace_adds_guards_and_slots() -> None:
    trace = [
        {"op": "goto", "url": f"https://{DOMAIN}/menu"},
        {"op": "fill_form", "fields": {"name": "{customer_name}"}},
        {"op": "confirm_order", "selector": "css:.submit"},
        {"op": "dance", "selector": "css:.nope"},  # unknown ops are dropped
    ]
    workflow = compile_trace(trace, action_key="create_order", target_domain=DOMAIN)

    assert [s.op for s in workflow.steps] == ["goto", "fill_form", "confirm_order"]
    assert workflow.steps[1].never_fill  # form steps always carry the refusal list
    assert workflow.steps[2].requires == "platform_confirmed_action"
    assert workflow.steps[2].capture == "order_reference"
    assert "customer_name" in workflow.parameter_names()
