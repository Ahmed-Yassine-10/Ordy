"""Action-gate + red-team suite (doc 03 §9, doc 08 §6).

Every attack here must be blocked by a DETERMINISTIC layer — a code branch, not a
model's refusal. These run with no provider, no DB, no network.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from ordy_tools.catalog import CREATE_ORDER, MAKE_RESERVATION, get_tool, manifest
from ordy_tools.confirm import (
    ConfirmationState,
    interpret_response,
    request_confirmation,
    resolve_confirmation,
)
from ordy_tools.executor import NativeAdapter, execute_action
from ordy_tools.models import (
    ACTION_BUDGET_EXCEEDED,
    ORDER_ABOVE_CAP,
    ORDER_BELOW_DELIVERY_MINIMUM,
    OUTSIDE_OPERATING_HOURS,
    PRODUCT_NOT_FOUND,
    PRODUCT_UNAVAILABLE,
    QUANTITY_ABOVE_CAP,
    SCHEMA_INVALID,
    TOOL_NOT_ENABLED,
    VARIANT_REQUIRED,
    ActionStatus,
)
from ordy_tools.policy import (
    Caps,
    DeliveryPolicy,
    PolicyContext,
    ToolBinding,
    validate_action,
)
from ordy_tools.pricing import ProductSnapshot, VariantSnapshot

PEP = "11111111-1111-1111-1111-111111111111"
MARG = "22222222-2222-2222-2222-222222222222"
LARGE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEDIUM = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OTHER_TENANT_PRODUCT = "99999999-9999-9999-9999-999999999999"


def _menu() -> dict[str, ProductSnapshot]:
    return {
        PEP: ProductSnapshot(
            product_id=PEP, name="Pizza Pepperoni", currency="TND",
            variants={
                LARGE: VariantSnapshot(LARGE, "Large", 32_000),
                MEDIUM: VariantSnapshot(MEDIUM, "Medium", 24_000),
            },
        ),
        MARG: ProductSnapshot(product_id=MARG, name="Margherita", currency="TND", price_minor=18_500),
    }


def _ctx(**overrides) -> PolicyContext:
    ctx = PolicyContext(
        channel="sandbox",
        currency="TND",
        bindings={
            "create_order": ToolBinding("create_order", enabled=True, channels=["sandbox"]),
            "make_reservation": ToolBinding("make_reservation", enabled=True, channels=["sandbox"]),
        },
        menu=_menu(),
        service_open={"pickup": True, "delivery": True, "dine_in": True, "reservation": True},
        delivery=DeliveryPolicy(in_zone=True, min_order_minor=25_000),
        caps=Caps(),
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def _order(items=None, order_type="pickup") -> dict:
    return {"type": order_type, "items": items or [{"product_id": PEP, "variant_id": LARGE, "quantity": 1}]}


# ---------- happy path ----------


def test_valid_order_passes_and_is_priced_server_side() -> None:
    report = validate_action(CREATE_ORDER, _order(), _ctx())
    assert report.passed
    assert report.total_minor == 32_000
    assert report.requires_confirmation is True
    assert "32.000 TND" in report.summary
    assert "1× Pizza Pepperoni (Large)" in report.summary


def test_model_supplied_total_is_ignored() -> None:
    """RED TEAM: injected/hallucinated discount. The total comes from the menu only."""
    args = _order()
    args["total_minor"] = 1  # model claims the order costs 0.001 TND
    args["discount_percent"] = 100
    report = validate_action(CREATE_ORDER, args, _ctx())
    # Unknown properties are rejected outright; even if they slipped through, pricing
    # never reads them.
    assert not report.passed and report.rejection_code == SCHEMA_INVALID
    clean = validate_action(CREATE_ORDER, _order(), _ctx())
    assert clean.total_minor == 32_000  # unchanged by any model assertion


# ---------- red team: whitelist ----------


def test_unknown_tool_is_not_in_the_catalog() -> None:
    """RED TEAM: 'grant_discount' cannot be called because it does not exist."""
    assert get_tool("grant_discount") is None
    assert [m["name"] for m in manifest(["create_order", "grant_discount"])] == ["create_order"]


def test_disabled_tool_is_blocked() -> None:
    ctx = _ctx(bindings={"create_order": ToolBinding("create_order", enabled=False)})
    report = validate_action(CREATE_ORDER, _order(), ctx)
    assert not report.passed and report.rejection_code == TOOL_NOT_ENABLED


def test_channel_restriction_is_enforced() -> None:
    ctx = _ctx(bindings={"create_order": ToolBinding("create_order", enabled=True, channels=["voice_phone"])})
    report = validate_action(CREATE_ORDER, _order(), ctx)
    assert not report.passed and report.rejection_code == "CHANNEL_NOT_ALLOWED"


# ---------- red team: schema + referential ----------


def test_schema_violations_are_rejected() -> None:
    assert validate_action(CREATE_ORDER, {"items": []}, _ctx()).rejection_code == SCHEMA_INVALID
    bad_type = {"type": "teleport", "items": [{"product_id": PEP, "quantity": 1}]}
    assert validate_action(CREATE_ORDER, bad_type, _ctx()).rejection_code == SCHEMA_INVALID
    bad_qty = _order([{"product_id": PEP, "variant_id": LARGE, "quantity": 0}])
    assert validate_action(CREATE_ORDER, bad_qty, _ctx()).rejection_code == SCHEMA_INVALID


def test_cross_tenant_product_is_not_found() -> None:
    """RED TEAM: a product id from another restaurant is simply not in this snapshot."""
    args = _order([{"product_id": OTHER_TENANT_PRODUCT, "quantity": 1}])
    report = validate_action(CREATE_ORDER, args, _ctx())
    assert not report.passed and report.rejection_code == PRODUCT_NOT_FOUND


def test_unavailable_item_is_blocked() -> None:
    menu = _menu()
    menu[MARG].is_available = False
    args = _order([{"product_id": MARG, "quantity": 1}])
    report = validate_action(CREATE_ORDER, args, _ctx(menu=menu))
    assert not report.passed and report.rejection_code == PRODUCT_UNAVAILABLE


def test_variant_required_when_product_has_options() -> None:
    args = _order([{"product_id": PEP, "quantity": 1}])
    report = validate_action(CREATE_ORDER, args, _ctx())
    assert not report.passed and report.rejection_code == VARIANT_REQUIRED
    assert "Large" in report.human_message  # the repair prompt names the options


# ---------- red team: business rules + caps ----------


def test_closed_service_is_blocked() -> None:
    ctx = _ctx(service_open={"pickup": False, "delivery": False, "dine_in": False, "reservation": False})
    report = validate_action(CREATE_ORDER, _order(), ctx)
    assert not report.passed and report.rejection_code == OUTSIDE_OPERATING_HOURS


def test_delivery_minimum_is_enforced() -> None:
    args = _order([{"product_id": MARG, "quantity": 1}], order_type="delivery")  # 18.5 < 25
    report = validate_action(CREATE_ORDER, args, _ctx())
    assert not report.passed and report.rejection_code == ORDER_BELOW_DELIVERY_MINIMUM
    assert "25.000 TND" in report.human_message


def test_quantity_cap_blocks_overflow_order() -> None:
    """RED TEAM: '999 pizzas'. Schema caps at 20; caps layer independently agrees."""
    args = _order([{"product_id": PEP, "variant_id": LARGE, "quantity": 999}])
    assert validate_action(CREATE_ORDER, args, _ctx()).rejection_code == SCHEMA_INVALID
    ctx = _ctx(caps=Caps(max_item_quantity=5))
    args_ok_schema = _order([{"product_id": PEP, "variant_id": LARGE, "quantity": 10}])
    assert validate_action(CREATE_ORDER, args_ok_schema, ctx).rejection_code == QUANTITY_ABOVE_CAP


def test_order_value_cap_is_enforced() -> None:
    ctx = _ctx(caps=Caps(max_order_minor=50_000))
    args = _order([{"product_id": PEP, "variant_id": LARGE, "quantity": 3}])  # 96.000
    report = validate_action(CREATE_ORDER, args, ctx)
    assert not report.passed and report.rejection_code == ORDER_ABOVE_CAP


def test_tenant_caps_can_only_tighten() -> None:
    binding = ToolBinding("create_order", enabled=True, channels=["sandbox"], caps={"max_order_minor": 10_000_000})
    ctx = _ctx(bindings={"create_order": binding}, caps=Caps(max_order_minor=50_000))
    args = _order([{"product_id": PEP, "variant_id": LARGE, "quantity": 3}])
    # Tenant tried to RAISE the cap; the platform ceiling still applies.
    assert validate_action(CREATE_ORDER, args, ctx).rejection_code == ORDER_ABOVE_CAP


def test_action_budget_is_enforced() -> None:
    ctx = _ctx(actions_taken=5, caps=Caps(max_actions_per_conversation=5))
    report = validate_action(CREATE_ORDER, _order(), ctx)
    assert not report.passed and report.rejection_code == ACTION_BUDGET_EXCEEDED


def test_reservation_party_size_cap() -> None:
    report = validate_action(MAKE_RESERVATION, {"party_size": 40, "starts_at": "2026-08-01T19:00:00Z"}, _ctx())
    assert not report.passed and report.rejection_code == QUANTITY_ABOVE_CAP


# ---------- confirmation gate ----------


def test_confirmation_expires_on_time_and_on_turn_distance() -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    req = request_confirmation(
        action_id="a1", tool_key="create_order", summary="s", args={}, now=now, turn_seq=4
    )
    late = resolve_confirmation(req, approved=True, now=now + timedelta(seconds=200), current_turn_seq=5)
    assert late is ConfirmationState.EXPIRED

    req2 = request_confirmation(
        action_id="a2", tool_key="create_order", summary="s", args={}, now=now, turn_seq=1
    )
    stale = resolve_confirmation(req2, approved=True, now=now, current_turn_seq=9)
    assert stale is ConfirmationState.EXPIRED  # "yes" 8 turns later is not consent


def test_confirmation_happy_and_decline() -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    req = request_confirmation(action_id="a", tool_key="create_order", summary="s", args={}, now=now, turn_seq=2)
    assert resolve_confirmation(req, approved=True, now=now, current_turn_seq=3) is ConfirmationState.CONFIRMED
    req2 = request_confirmation(action_id="b", tool_key="create_order", summary="s", args={}, now=now, turn_seq=2)
    assert resolve_confirmation(req2, approved=False, now=now, current_turn_seq=3) is ConfirmationState.DECLINED


def test_ambiguous_response_is_not_consent() -> None:
    assert interpret_response("yes") is True
    assert interpret_response("oui") is True
    assert interpret_response("no") is False
    assert interpret_response("hmm, what's in it?") is None  # unclear ≠ approval
    assert interpret_response("") is None


# ---------- executor ----------


def test_execution_is_idempotent_and_output_validated() -> None:
    async def run():
        adapter = NativeAdapter()
        first = await execute_action(CREATE_ORDER, _order(), adapter, idempotency_key="idem-key-1")
        second = await execute_action(CREATE_ORDER, _order(), adapter, idempotency_key="idem-key-1")
        return first, second

    first, second = asyncio.run(run())
    assert first.status is ActionStatus.SUCCEEDED
    assert first.output["order_id"] == second.output["order_id"]  # replay ≠ double-create


def test_bad_adapter_output_fails_validation() -> None:
    class BrokenAdapter:
        name = "broken"

        async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
            return {"unexpected": True}  # missing required order_id/status

    outcome = asyncio.run(execute_action(CREATE_ORDER, _order(), BrokenAdapter(), idempotency_key="k"))
    assert outcome.status is ActionStatus.FAILED
    assert outcome.error["type"] == "OutputSchemaViolation"
