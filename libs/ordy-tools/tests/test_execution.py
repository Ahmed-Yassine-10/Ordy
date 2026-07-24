"""Execution tests: fallback chain, compensation, Action Provider conformance, webhooks."""

from __future__ import annotations

import asyncio
import json

from ordy_core.webhooks import build_envelope, next_retry_delay, sign, verify
from ordy_tools.adapters import FallbackAdapter, ProviderError, RestAdapter
from ordy_tools.catalog import CREATE_ORDER, PLATFORM_TOOLS
from ordy_tools.conformance import run_conformance
from ordy_tools.executor import NativeAdapter, execute_action, execute_plan
from ordy_tools.models import ActionStatus

ORDER_ARGS = {"type": "pickup", "items": [{"product_id": "p", "quantity": 1}]}


# ---------- fake Action Provider ----------


class FakeProvider:
    """A conformant provider: honors Idempotency-Key, returns the documented shapes."""

    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.create_calls = 0

    async def post(self, path: str, payload: dict, *, idempotency_key: str) -> dict:
        if path == "/ordy/orders":
            self.create_calls += 1
            if idempotency_key in self.orders:
                return self.orders[idempotency_key]
            result = {"ref": f"R{len(self.orders) + 1}", "status": "confirmed", "eta_minutes": 15}
            self.orders[idempotency_key] = result
            return result
        if path.endswith("/cancel"):
            return {"cancelled": True}
        if path == "/ordy/reservations":
            return {"ref": "V1", "status": "confirmed"}
        raise ProviderError(f"unknown path {path}")

    async def get(self, path: str, params: dict | None = None) -> dict:
        if path == "/ordy/menu":
            return {"items": [{"ref": "p", "name": "Pizza", "price_minor": 32000}]}
        if path.startswith("/ordy/orders/"):
            return {"status": "preparing"}
        if path == "/ordy/availability":
            return {"available": True}
        raise ProviderError(f"unknown path {path}")


class BrokenProvider(FakeProvider):
    """Creates a NEW order on every call — the unsafe behavior conformance must catch."""

    async def post(self, path: str, payload: dict, *, idempotency_key: str) -> dict:
        if path == "/ordy/orders":
            self.create_calls += 1
            return {"ref": f"R{self.create_calls}", "status": "confirmed"}
        return await super().post(path, payload, idempotency_key=idempotency_key)


class DeadProvider:
    async def post(self, path: str, payload: dict, *, idempotency_key: str) -> dict:
        raise ProviderError("provider unreachable")

    async def get(self, path: str, params: dict | None = None) -> dict:
        raise ProviderError("provider unreachable")


# ---------- RestAdapter ----------


def test_rest_adapter_maps_create_order() -> None:
    out = asyncio.run(RestAdapter(FakeProvider()).execute("create_order", ORDER_ARGS, idempotency_key="k1"))
    assert out["order_id"] == "R1" and out["status"] == "confirmed"


def test_rest_adapter_idempotent_replay() -> None:
    provider = FakeProvider()
    adapter = RestAdapter(provider)

    async def run():
        a = await adapter.execute("create_order", ORDER_ARGS, idempotency_key="same")
        b = await adapter.execute("create_order", ORDER_ARGS, idempotency_key="same")
        return a, b

    first, second = asyncio.run(run())
    assert first["order_id"] == second["order_id"]
    assert len(provider.orders) == 1  # one real order despite two calls


# ---------- fallback: an integration outage must never lose the order ----------


def test_fallback_to_native_when_provider_is_down() -> None:
    notes: list[str] = []
    adapter = FallbackAdapter(
        RestAdapter(DeadProvider()), NativeAdapter(), on_fallback=lambda tool, exc: notes.append(tool)
    )
    outcome = asyncio.run(execute_action(CREATE_ORDER, ORDER_ARGS, adapter, idempotency_key="k"))

    assert outcome.status is ActionStatus.SUCCEEDED  # order captured, not dropped
    assert adapter.used_fallback is True
    assert adapter.name == "native"
    assert notes == ["create_order"]  # staff/ops notified


def test_no_fallback_when_primary_succeeds() -> None:
    adapter = FallbackAdapter(RestAdapter(FakeProvider()), NativeAdapter())
    outcome = asyncio.run(execute_action(CREATE_ORDER, ORDER_ARGS, adapter, idempotency_key="k"))
    assert outcome.status is ActionStatus.SUCCEEDED
    assert adapter.used_fallback is False and adapter.name == "rest"


# ---------- compensation ----------


def test_failed_later_step_compensates_earlier_ones() -> None:
    calls: list[str] = []

    class RecordingAdapter(NativeAdapter):
        name = "recording"

        async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
            calls.append(tool_key)
            if tool_key == "make_reservation":
                raise RuntimeError("reservation system down")
            return await super().execute(tool_key, args, idempotency_key=idempotency_key)

    steps = [
        (PLATFORM_TOOLS["create_order"], ORDER_ARGS),
        (PLATFORM_TOOLS["make_reservation"], {"party_size": 2, "starts_at": "2026-08-01T19:00:00Z"}),
    ]
    outcomes = asyncio.run(execute_plan(steps, RecordingAdapter(), PLATFORM_TOOLS))

    assert outcomes[0].status is ActionStatus.SUCCEEDED
    assert outcomes[1].status is ActionStatus.FAILED
    assert "cancel_order" in calls  # the created order was rolled back


# ---------- conformance ----------


def test_conformant_provider_passes() -> None:
    report = asyncio.run(run_conformance(FakeProvider()))
    assert report.passed
    assert {c.name for c in report.checks} >= {"menu_endpoint", "create_order", "idempotency"}


def test_non_idempotent_provider_fails_conformance() -> None:
    report = asyncio.run(run_conformance(BrokenProvider()))
    assert not report.passed
    idempotency = next(c for c in report.checks if c.name == "idempotency")
    assert not idempotency.passed and "NEW order" in idempotency.detail


def test_dead_provider_fails_conformance() -> None:
    assert not asyncio.run(run_conformance(DeadProvider())).passed


# ---------- webhooks ----------


def test_signature_roundtrip_and_tamper_detection() -> None:
    secret = b"whsec_test"
    envelope = build_envelope(
        event_id="evt_1", event_type="order.created", restaurant_id="res_1",
        created_at="2026-07-24T18:00:00Z", data={"order": {"ref": "A1"}},
    )
    signed = sign(secret, envelope, timestamp=1_784_841_600)

    assert verify(secret, body=signed.body, signature=signed.signature,
                  timestamp=signed.timestamp, now=signed.timestamp + 10)
    # tampered body
    assert not verify(secret, body=signed.body.replace("A1", "A2"), signature=signed.signature,
                      timestamp=signed.timestamp, now=signed.timestamp + 10)
    # wrong secret
    assert not verify(b"other", body=signed.body, signature=signed.signature,
                      timestamp=signed.timestamp, now=signed.timestamp + 10)


def test_replay_outside_tolerance_is_rejected() -> None:
    secret = b"whsec_test"
    envelope = build_envelope(
        event_id="e", event_type="order.confirmed", restaurant_id="r",
        created_at="2026-07-24T18:00:00Z", data={},
    )
    signed = sign(secret, envelope, timestamp=1_000_000)
    assert not verify(secret, body=signed.body, signature=signed.signature,
                      timestamp=signed.timestamp, now=1_000_000 + 3_600)


def test_envelope_rejects_unknown_event_types() -> None:
    try:
        build_envelope(event_id="e", event_type="order.exploded", restaurant_id="r",
                       created_at="now", data={})
    except ValueError as exc:
        assert "unknown event type" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_signed_body_is_canonical_json() -> None:
    envelope = build_envelope(event_id="e", event_type="order.created", restaurant_id="r",
                              created_at="t", data={"b": 2, "a": 1})
    signed = sign(b"s", envelope, timestamp=1)
    assert json.loads(signed.body)["data"] == {"a": 1, "b": 2}
    assert signed.body.index('"a"') < signed.body.index('"b"')  # deterministic ordering


def test_retry_schedule_terminates() -> None:
    assert next_retry_delay(0) == 60
    assert next_retry_delay(4) == 21_600
    assert next_retry_delay(5) is None  # dead-letter
