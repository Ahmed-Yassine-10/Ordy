"""Trace → workflow compilation (doc 04 §6 step 2).

An exploration agent records what it did on the site; this turns that trace into a
declarative workflow: concrete values become `{parameter}` slots, each step gets an
expected-state assertion, form steps inherit the never-fill guard, and the final submit
is marked as requiring a platform-confirmed action.

Compilation is deterministic — the AI's role ended when it produced the trace, and a
human still approves the result before it can run.
"""

from __future__ import annotations

from ordy_automation.models import Step, WorkflowDefinition
from ordy_automation.safety import NEVER_FILL_PATTERNS

# Recorded value → slot name. Whatever the explorer typed becomes a parameter.
DEFAULT_SLOTS = {
    "product_query": "{product_query}",
    "variant_label": "{variant_label}",
    "quantity": "{quantity}",
    "customer_name": "{customer_name}",
    "phone": "{phone}",
}

_EXPECTATIONS = {
    "goto": None,
    "search_click": "item_page_or_modal",
    "select_option": "option_selected",
    "click": "cart_count_increased",
    "goto_cart_checkout": "checkout_form_visible",
    "fill_form": "form_filled",
    "confirm_order": "order_confirmation_visible",
}


def compile_trace(
    trace: list[dict], *, action_key: str, target_domain: str, workflow_id: str = "wf_draft"
) -> WorkflowDefinition:
    steps: list[Step] = []
    for entry in trace:
        op = str(entry.get("op", ""))
        if op not in _EXPECTATIONS:
            continue  # unknown recorded ops are dropped rather than guessed at

        step = Step(
            op=op,
            target=entry.get("target"),
            url=entry.get("url"),
            strategy=list(entry.get("strategy") or ([entry["selector"]] if entry.get("selector") else [])),
            value=entry.get("value"),
            fields=dict(entry.get("fields") or {}),
            expect=_EXPECTATIONS[op],
            capture=entry.get("capture"),
        )
        if op == "fill_form":
            # Form steps always carry the refusal list, even if the trace never saw a
            # payment field — drift must not be able to introduce one silently.
            step.never_fill = list(NEVER_FILL_PATTERNS)
        if op == "confirm_order":
            step.requires = "platform_confirmed_action"
            step.capture = step.capture or "order_reference"
        steps.append(step)

    return WorkflowDefinition(
        workflow_id=workflow_id, action_key=action_key, target_domain=target_domain, steps=steps
    )
