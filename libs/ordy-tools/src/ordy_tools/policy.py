"""The deterministic policy engine (doc 03 §3.4) — the core invariant.

Ordered, fail-fast, every step recorded:
  whitelist → schema → referential integrity + server-side pricing → business rules
  → caps/anomaly → confirmation requirement

This is CODE, not a prompt. The model cannot raise caps, enable tools, alter prices, or
skip confirmation: those live in tables it cannot address and branches it cannot reach.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ordy_tools.models import (
    ACTION_BUDGET_EXCEEDED,
    CHANNEL_NOT_ALLOWED,
    ORDER_ABOVE_CAP,
    ORDER_BELOW_DELIVERY_MINIMUM,
    OUTSIDE_DELIVERY_ZONE,
    OUTSIDE_OPERATING_HOURS,
    QUANTITY_ABOVE_CAP,
    SCHEMA_INVALID,
    TOO_MANY_ITEMS,
    TOOL_NOT_ENABLED,
    CheckResult,
    ToolSpec,
    ValidationReport,
)
from ordy_tools.pricing import ProductSnapshot, format_money, price_items
from ordy_tools.schema import SchemaValidator, default_validator


@dataclass(slots=True)
class Caps:
    max_order_minor: int = 500_000
    max_item_quantity: int = 20
    max_items: int = 30
    max_party_size: int = 20
    max_actions_per_conversation: int = 5

    def tightened_by(self, overrides: dict) -> "Caps":
        """Tenant overrides may only TIGHTEN platform caps (doc 06 §3.6)."""
        return Caps(
            max_order_minor=min(self.max_order_minor, overrides.get("max_order_minor", self.max_order_minor)),
            max_item_quantity=min(self.max_item_quantity, overrides.get("max_item_quantity", self.max_item_quantity)),
            max_items=min(self.max_items, overrides.get("max_items", self.max_items)),
            max_party_size=min(self.max_party_size, overrides.get("max_party_size", self.max_party_size)),
            max_actions_per_conversation=min(
                self.max_actions_per_conversation,
                overrides.get("max_actions_per_conversation", self.max_actions_per_conversation),
            ),
        )


@dataclass(slots=True)
class ToolBinding:
    tool_key: str
    enabled: bool = False
    adapter: str = "native"
    channels: list[str] = field(default_factory=lambda: ["voice_web", "voice_phone", "text_widget", "sandbox"])
    caps: dict = field(default_factory=dict)


@dataclass(slots=True)
class DeliveryPolicy:
    in_zone: bool = True
    min_order_minor: int = 0
    fee_minor: int = 0


@dataclass(slots=True)
class PolicyContext:
    """Everything the gate needs, resolved from the DB by the caller (never by the model)."""

    channel: str = "sandbox"
    currency: str = "TND"
    bindings: dict[str, ToolBinding] = field(default_factory=dict)
    menu: dict[str, ProductSnapshot] = field(default_factory=dict)
    service_open: dict[str, bool] = field(default_factory=dict)  # pickup|delivery|dine_in|reservation
    delivery: DeliveryPolicy = field(default_factory=DeliveryPolicy)
    caps: Caps = field(default_factory=Caps)
    actions_taken: int = 0


# ---- named validators (referenced by ToolSpec.validators, run in order) ----


def _v_items_available(spec: ToolSpec, args: dict, ctx: PolicyContext, report: ValidationReport) -> CheckResult:
    """Referential integrity + SERVER-SIDE PRICING. Any client/model total is discarded."""
    result = price_items(args.get("items", []), ctx.menu)
    if not result.ok:
        return CheckResult("items_available", False, result.error_code, result.error_message)
    report.total_minor = result.total_minor
    report.currency = ctx.currency
    report.priced_items = [
        {
            "product_id": i.product_id, "name": i.name, "variant_id": i.variant_id,
            "variant_name": i.variant_name, "quantity": i.quantity,
            "unit_price_minor": i.unit_price_minor, "total_minor": i.total_minor,
        }
        for i in result.items
    ]
    return CheckResult("items_available", True, data={"total_minor": result.total_minor})


def _v_open_hours(spec: ToolSpec, args: dict, ctx: PolicyContext, report: ValidationReport) -> CheckResult:
    service = args.get("type", "pickup")
    if not ctx.service_open.get(service, False):
        return CheckResult(
            "open_hours", False, OUTSIDE_OPERATING_HOURS,
            f"We're not taking {service.replace('_', ' ')} orders right now.",
        )
    return CheckResult("open_hours", True)


def _v_delivery_zone(spec: ToolSpec, args: dict, ctx: PolicyContext, report: ValidationReport) -> CheckResult:
    if args.get("type") != "delivery":
        return CheckResult("delivery_zone", True, data={"skipped": True})
    if not ctx.delivery.in_zone:
        return CheckResult("delivery_zone", False, OUTSIDE_DELIVERY_ZONE, "That address is outside our delivery area.")
    total = report.total_minor or 0
    if total < ctx.delivery.min_order_minor:
        return CheckResult(
            "delivery_zone", False, ORDER_BELOW_DELIVERY_MINIMUM,
            f"Delivery needs a minimum of {format_money(ctx.delivery.min_order_minor, ctx.currency)} — "
            f"you're at {format_money(total, ctx.currency)}.",
        )
    return CheckResult("delivery_zone", True)


def _v_order_caps(spec: ToolSpec, args: dict, ctx: PolicyContext, report: ValidationReport) -> CheckResult:
    caps = ctx.caps.tightened_by(ctx.bindings.get(spec.key, ToolBinding(spec.key)).caps)
    items = args.get("items", [])
    if len(items) > caps.max_items:
        return CheckResult("order_caps", False, TOO_MANY_ITEMS, "That's more items than I can put in one order.")
    for item in items:
        if int(item.get("quantity", 1)) > caps.max_item_quantity:
            return CheckResult(
                "order_caps", False, QUANTITY_ABOVE_CAP,
                f"I can only order up to {caps.max_item_quantity} of one item at a time.",
            )
    total = report.total_minor or 0
    if total > caps.max_order_minor:
        return CheckResult(
            "order_caps", False, ORDER_ABOVE_CAP,
            f"That order is above the {format_money(caps.max_order_minor, ctx.currency)} limit I can place — "
            "let me get a colleague to help.",
        )
    return CheckResult("order_caps", True)


def _v_reservation_rules(spec: ToolSpec, args: dict, ctx: PolicyContext, report: ValidationReport) -> CheckResult:
    caps = ctx.caps.tightened_by(ctx.bindings.get(spec.key, ToolBinding(spec.key)).caps)
    if not ctx.service_open.get("reservation", False):
        return CheckResult("reservation_rules", False, OUTSIDE_OPERATING_HOURS, "We're not taking bookings for that time.")
    if int(args.get("party_size", 1)) > caps.max_party_size:
        return CheckResult(
            "reservation_rules", False, QUANTITY_ABOVE_CAP,
            f"For parties over {caps.max_party_size} I'll put you through to the team.",
        )
    return CheckResult("reservation_rules", True)


def _v_action_budget(spec: ToolSpec, args: dict, ctx: PolicyContext, report: ValidationReport) -> CheckResult:
    caps = ctx.caps.tightened_by(ctx.bindings.get(spec.key, ToolBinding(spec.key)).caps)
    if ctx.actions_taken >= caps.max_actions_per_conversation:
        return CheckResult(
            "action_budget", False, ACTION_BUDGET_EXCEEDED,
            "We've done a lot in this conversation — let me hand you to a colleague.",
        )
    return CheckResult("action_budget", True)


VALIDATORS = {
    "items_available": _v_items_available,
    "open_hours": _v_open_hours,
    "delivery_zone": _v_delivery_zone,
    "order_caps": _v_order_caps,
    "reservation_rules": _v_reservation_rules,
    "action_budget": _v_action_budget,
}


def build_summary(spec: ToolSpec, args: dict, report: ValidationReport) -> str:
    """System-generated confirmation text — spoken/shown VERBATIM (doc 05 §5)."""
    if spec.key == "create_order":
        parts = []
        for item in report.priced_items:
            label = f"{item['quantity']}× {item['name']}"
            if item.get("variant_name"):
                label += f" ({item['variant_name']})"
            parts.append(label)
        mode = str(args.get("type", "pickup")).replace("_", " ")
        total = format_money(report.total_minor or 0, report.currency or "TND")
        return f"{', '.join(parts)} — {mode} — total {total}"
    if spec.key == "make_reservation":
        return f"Table for {args.get('party_size')} at {args.get('starts_at')}"
    if spec.key == "cancel_order":
        return f"Cancel order {args.get('order_ref')}"
    return spec.title


def validate_action(
    spec: ToolSpec,
    args: dict,
    ctx: PolicyContext,
    *,
    validator: SchemaValidator | None = None,
) -> ValidationReport:
    """Run the full gate. Fail-fast; the report records every check attempted."""
    report = ValidationReport()

    # 1) Whitelist — the tool must be enabled for this tenant AND this channel.
    binding = ctx.bindings.get(spec.key)
    if binding is None or not binding.enabled:
        report.add(CheckResult("whitelist", False, TOOL_NOT_ENABLED, "I can't do that here."))
        return _reject(report)
    if ctx.channel not in binding.channels:
        report.add(CheckResult("whitelist", False, CHANNEL_NOT_ALLOWED, "I can't do that on this channel."))
        return _reject(report)
    report.add(CheckResult("whitelist", True))

    # 2) Schema.
    errors = (validator or default_validator()).validate(args, spec.input_schema)
    if errors:
        report.add(CheckResult("schema", False, SCHEMA_INVALID, "; ".join(errors[:3])))
        return _reject(report)
    report.add(CheckResult("schema", True))

    # 3-5) Referential + pricing, business rules, caps — in the order the spec declares.
    for name in spec.validators:
        check_fn = VALIDATORS.get(name)
        if check_fn is None:
            continue
        result = check_fn(spec, args, ctx, report)
        report.add(result)
        if not result.passed:
            return _reject(report)

    # 6) Confirmation requirement.
    report.passed = True
    report.requires_confirmation = spec.requires_confirmation
    report.summary = build_summary(spec, args, report)
    return report


def _reject(report: ValidationReport) -> ValidationReport:
    failed = next((c for c in report.checks if not c.passed), None)
    report.passed = False
    report.rejection_code = failed.code if failed else None
    report.human_message = failed.message if failed else None
    return report
