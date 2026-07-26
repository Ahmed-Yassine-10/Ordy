"""Al Ostedh provider tests — the real-integration adapter, proven without a network.

These exercise the FULL gate against a fake transport seeded with the platform's real menu
shape (float TND prices, flat products). Every guarantee Ordy adds on top of Al Ostedh's own
assistant is asserted here: server-side pricing, caps, deterministic confirmation, idempotency,
fallback, the model's inability to set contact details — and now the config-driven path: the
endpoint comes from an approved ordy.config.json, and an UNAPPROVED config cannot place orders.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from ordy_tools.catalog import CREATE_ORDER, PLATFORM_TOOLS
from ordy_tools.confirm import (
    ConfirmationState,
    interpret_response,
    request_confirmation,
    resolve_confirmation,
)
from ordy_tools.executor import NativeAdapter, execute_action
from ordy_tools.models import ActionStatus, QUANTITY_ABOVE_CAP
from ordy_tools.policy import PolicyContext, ToolBinding, validate_action
from ordy_tools.providers.alostedh import (
    AlOstedhAdapter,
    CustomerContext,
    adapter_from_config,
    menu_snapshot,
    to_major,
    to_minor,
)
from ordy_tools.providers.config_loader import ConsentError, load_config

# A slice of the platform's real catalog (see GET /api/products on al-ostedh-api.vercel.app).
PRODUCTS = [
    {"id": "7a71ce69-2d93-4244-807f-672f090f6e3f", "name": "Burger Crispy Normal", "price": 7.9, "isAvailable": True},
    {"id": "087491b1-7554-481c-9039-46e69b0c1af1", "name": "Burger Crispy Double", "price": 10.5, "isAvailable": True},
    {"id": "376442dd-4764-4eb8-be52-819d043a1eb2", "name": "Burger Crispy Grand", "price": 13.9, "isAvailable": False},
]

CUSTOMER = CustomerContext(contact_name="Test Client", contact_phone="+21620000000", payment_method="CASH")

# An approved config as @ordy/analyze would emit for Al Ostedh.
SAMPLE_CONFIG = {
    "restaurant": {"name": "Al Ostedh", "currency": "TND"},
    "capabilities": [
        {"action": "create_order", "binding": "rest", "method": "POST", "path": "/api/orders", "auth": "bearer", "confidence": 0.95},
        {"action": "check_availability", "binding": "rest", "method": "GET", "path": "/api/products", "auth": "none", "confidence": 0.8},
        {"action": "make_reservation", "binding": "native", "confidence": 0},
    ],
    "consent": {"approved": True, "approvedBy": "Ahmed Yassine", "approvedAt": "2026-07-25T00:00:00Z"},
}


class FakeTransport:
    """Stand-in for the Al Ostedh REST API. Records method+path and order payloads."""

    def __init__(self) -> None:
        self.created: list[dict] = []
        self.calls: list[tuple[str, str]] = []
        self.next_id = 1

    async def request(self, method, path, *, json=None, params=None, auth=False, idempotency_key=None) -> dict:
        self.calls.append((method, path))
        if method == "POST" and json is not None and "items" in json:
            self.created.append(json)
            prices = {p["id"]: p["price"] for p in PRODUCTS}
            total = sum(prices[i["productId"]] * i["quantity"] for i in json["items"])
            oid = f"ord-{self.next_id}"
            self.next_id += 1
            return {"id": oid, "totalAmount": round(total, 3), "status": "PENDING"}
        if method == "GET":
            return {"id": path.rsplit("/", 1)[-1], "status": "PREPARING"}
        return {}


class DeadTransport:
    async def request(self, *a, **k) -> dict:
        raise ConnectionError("al-ostedh-api unreachable")


def _ctx() -> PolicyContext:
    return PolicyContext(
        channel="text_widget",
        currency="TND",
        bindings={"create_order": ToolBinding("create_order", enabled=True, adapter="alostedh")},
        menu=menu_snapshot(PRODUCTS),
        service_open={"pickup": True, "delivery": True, "dine_in": True},
    )


# ---------------------------------------------------------------- money mapping


def test_to_minor_has_no_float_noise() -> None:
    assert to_minor(7.9) == 7900
    assert to_minor(10.5) == 10500
    assert to_minor(13.9) == 13900  # the value that would be 13900.0000002 via naive *1000
    assert to_minor(16) == 16000
    assert to_major(13900) == "13.900" and to_major(7900) == "7.900"


def test_menu_snapshot_maps_price_and_availability() -> None:
    snap = menu_snapshot(PRODUCTS)
    assert snap["7a71ce69-2d93-4244-807f-672f090f6e3f"].price_minor == 7900
    assert snap["376442dd-4764-4eb8-be52-819d043a1eb2"].is_available is False


# ---------------------------------------------------------------- server-side pricing


def test_gate_prices_from_the_menu_not_the_model() -> None:
    args = {
        "type": "pickup",
        "items": [
            {"product_id": "7a71ce69-2d93-4244-807f-672f090f6e3f", "quantity": 2},
            {"product_id": "087491b1-7554-481c-9039-46e69b0c1af1", "quantity": 1},
        ],
    }
    report = validate_action(CREATE_ORDER, args, _ctx())
    assert report.passed
    assert report.total_minor == 7900 * 2 + 10500  # 26300 millimes, computed here
    assert "26.300 TND" in report.summary


def test_gate_rejects_unavailable_item() -> None:
    args = {"type": "pickup", "items": [{"product_id": "376442dd-4764-4eb8-be52-819d043a1eb2", "quantity": 1}]}
    assert not validate_action(CREATE_ORDER, args, _ctx()).passed


def test_gate_enforces_quantity_cap() -> None:
    normal = "7a71ce69-2d93-4244-807f-672f090f6e3f"
    schema_report = validate_action(CREATE_ORDER, {"type": "pickup", "items": [{"product_id": normal, "quantity": 99}]}, _ctx())
    assert not schema_report.passed and schema_report.rejection_code == "SCHEMA_INVALID"

    ctx = _ctx()
    ctx.bindings["create_order"] = ToolBinding("create_order", enabled=True, adapter="alostedh", caps={"max_item_quantity": 3})
    report = validate_action(CREATE_ORDER, {"type": "pickup", "items": [{"product_id": normal, "quantity": 5}]}, ctx)
    assert not report.passed and report.rejection_code == QUANTITY_ABOVE_CAP


# ---------------------------------------------------------------- payload mapping + contact safety


def test_adapter_maps_ordy_args_to_al_ostedh_payload() -> None:
    transport = FakeTransport()
    adapter = AlOstedhAdapter(transport, CUSTOMER)
    args = {
        "type": "delivery",
        "items": [{"product_id": "7a71ce69-2d93-4244-807f-672f090f6e3f", "quantity": 2, "note": "sans oignons"}],
    }
    out = asyncio.run(adapter.execute("create_order", args, idempotency_key="k1"))

    assert ("POST", "/api/orders") in transport.calls
    sent = transport.created[0]
    assert sent["deliveryMode"] == "DELIVERY"
    assert sent["items"] == [
        {"productId": "7a71ce69-2d93-4244-807f-672f090f6e3f", "quantity": 2, "customizationNotes": "sans oignons"}
    ]
    assert out["order_id"] == "ord-1" and out["status"] == "confirmed"
    assert out["total_minor"] == 15800 and out["currency"] == "TND"


def test_model_cannot_set_contact_details() -> None:
    transport = FakeTransport()
    adapter = AlOstedhAdapter(transport, CUSTOMER)
    args = {
        "type": "pickup",
        "items": [{"product_id": "7a71ce69-2d93-4244-807f-672f090f6e3f", "quantity": 1}],
        "contactPhone": "+216-attacker",
        "shippingAddress": "somewhere else",
    }
    asyncio.run(adapter.execute("create_order", args, idempotency_key="k2"))
    sent = transport.created[0]
    assert sent["contactPhone"] == "+21620000000"
    assert "shippingAddress" not in sent


# ---------------------------------------------------------------- idempotency


def test_adapter_is_idempotent_within_process() -> None:
    transport = FakeTransport()
    adapter = AlOstedhAdapter(transport, CUSTOMER)
    args = {"type": "pickup", "items": [{"product_id": "7a71ce69-2d93-4244-807f-672f090f6e3f", "quantity": 1}]}

    async def run() -> tuple[dict, dict]:
        a = await adapter.execute("create_order", args, idempotency_key="same")
        b = await adapter.execute("create_order", args, idempotency_key="same")
        return a, b

    first, second = asyncio.run(run())
    assert first["order_id"] == second["order_id"]
    assert len(transport.created) == 1  # ONE real order despite two calls


# ---------------------------------------------------------------- fallback: never lose the order


def test_fallback_to_native_when_al_ostedh_is_down() -> None:
    from ordy_tools.adapters import FallbackAdapter

    notified: list[str] = []
    adapter = FallbackAdapter(
        AlOstedhAdapter(DeadTransport(), CUSTOMER),
        NativeAdapter(),
        on_fallback=lambda tool, exc: notified.append(tool),
    )
    args = {"type": "pickup", "items": [{"product_id": "7a71ce69-2d93-4244-807f-672f090f6e3f", "quantity": 1}]}
    outcome = asyncio.run(execute_action(CREATE_ORDER, args, adapter, idempotency_key="k"))

    assert outcome.status is ActionStatus.SUCCEEDED
    assert adapter.used_fallback is True and adapter.name == "native"
    assert notified == ["create_order"]


# ---------------------------------------------------------------- config loader + consent


def test_load_config_parses_routes_and_consent() -> None:
    cfg = load_config(SAMPLE_CONFIG)
    assert cfg.consent_approved and cfg.consent_by == "Ahmed Yassine"
    assert cfg.rest_binding("create_order").path == "/api/orders"
    assert cfg.rest_binding("create_order").auth_required is True
    assert cfg.rest_binding("check_availability").auth_required is False
    assert "make_reservation" in cfg.native_actions


def test_unapproved_config_cannot_place_orders() -> None:
    unapproved = {**SAMPLE_CONFIG, "consent": {"approved": False, "approvedBy": None}}
    cfg = load_config(unapproved)
    with pytest.raises(ConsentError):
        adapter_from_config(cfg, FakeTransport(), CUSTOMER)


def test_adapter_from_config_uses_the_detected_path() -> None:
    # Prove the endpoint is taken from the config, not hardcoded: use a non-default path.
    custom = {**SAMPLE_CONFIG}
    custom["capabilities"] = [
        {"action": "create_order", "binding": "rest", "method": "POST", "path": "/api/v2/orders", "auth": "bearer", "confidence": 0.9},
    ]
    cfg = load_config(custom)
    transport = FakeTransport()
    adapter = adapter_from_config(cfg, transport, CUSTOMER)
    args = {"type": "pickup", "items": [{"product_id": "7a71ce69-2d93-4244-807f-672f090f6e3f", "quantity": 1}]}
    asyncio.run(adapter.execute("create_order", args, idempotency_key="cfg"))
    assert ("POST", "/api/v2/orders") in transport.calls  # followed the config, not the default


# ---------------------------------------------------------------- confirmation gate end-to-end


def test_full_gate_confirm_then_execute() -> None:
    transport = FakeTransport()
    adapter = AlOstedhAdapter(transport, CUSTOMER)
    ctx = _ctx()
    args = {"type": "pickup", "items": [{"product_id": "087491b1-7554-481c-9039-46e69b0c1af1", "quantity": 1}]}

    report = validate_action(CREATE_ORDER, args, ctx)
    assert report.passed and report.requires_confirmation

    now = datetime.now(UTC)
    req = request_confirmation(action_id="a1", tool_key="create_order", summary=report.summary, args=args, now=now, turn_seq=1)
    assert interpret_response("hmm, je sais pas") is None
    assert interpret_response("oui vas-y") is True

    state = resolve_confirmation(req, approved=True, now=now + timedelta(seconds=5), current_turn_seq=2)
    assert state is ConfirmationState.CONFIRMED

    outcome = asyncio.run(execute_action(PLATFORM_TOOLS["create_order"], args, adapter, idempotency_key="a1"))
    assert outcome.status is ActionStatus.SUCCEEDED
    assert outcome.external_ref == "ord-1" and outcome.adapter == "alostedh"


def test_stale_confirmation_is_rejected() -> None:
    now = datetime.now(UTC)
    req = request_confirmation(action_id="a2", tool_key="create_order", summary="…", args={}, now=now, turn_seq=1)
    state = resolve_confirmation(req, approved=True, now=now, current_turn_seq=5)
    assert state is ConfirmationState.EXPIRED
