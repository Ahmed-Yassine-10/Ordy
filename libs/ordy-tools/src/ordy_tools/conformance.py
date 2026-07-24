"""Action Provider conformance runner (doc 07 §6).

A restaurant's API must PROVE it behaves before the `rest` adapter may be bound to live
tools. The decisive check is idempotency: replaying a create with the same
`Idempotency-Key` must return the same reference, never a second order.

Runs against a marked test mode (`Ordy-Test: true`) — never real customer traffic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ordy_tools.adapters import ProviderClient

TEST_ORDER = {
    "type": "pickup",
    "items": [{"product_ref": "conformance-probe", "quantity": 1}],
    "customer": {"name": "Ordy Conformance", "phone": "+21600000000"},
}


@dataclass(slots=True)
class ConformanceCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class ConformanceReport:
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(ConformanceCheck(name=name, passed=passed, detail=detail))

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks],
        }


async def run_conformance(client: ProviderClient, *, probe_orders: bool = True) -> ConformanceReport:
    report = ConformanceReport()

    # 1) Menu endpoint — required for continuous sync.
    try:
        menu = await client.get("/ordy/menu")
        items = menu.get("items") if isinstance(menu, dict) else None
        report.add(
            "menu_endpoint",
            isinstance(items, list),
            "GET /ordy/menu must return {items: [...]}" if not isinstance(items, list) else "",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("menu_endpoint", False, f"{type(exc).__name__}: {exc}")

    if not probe_orders:
        return report

    # 2) Order creation returns a usable reference.
    key = "ordy-conformance-key-1"
    first_ref = None
    try:
        first = await client.post("/ordy/orders", TEST_ORDER, idempotency_key=key)
        first_ref = first.get("ref")
        report.add("create_order", bool(first_ref), "POST /ordy/orders must return {ref, status}")
    except Exception as exc:  # noqa: BLE001
        report.add("create_order", False, f"{type(exc).__name__}: {exc}")

    # 3) THE decisive check — replay must not create a second order.
    try:
        replay = await client.post("/ordy/orders", TEST_ORDER, idempotency_key=key)
        same = first_ref is not None and replay.get("ref") == first_ref
        report.add(
            "idempotency",
            same,
            "" if same else "replaying an Idempotency-Key created a NEW order — unsafe to bind",
        )
    except Exception as exc:  # noqa: BLE001
        report.add("idempotency", False, f"{type(exc).__name__}: {exc}")

    # 4) Status lookup for the order we just created.
    if first_ref:
        try:
            status = await client.get(f"/ordy/orders/{first_ref}")
            report.add("order_status", bool(status.get("status")), "GET /ordy/orders/{ref} must return {status}")
        except Exception as exc:  # noqa: BLE001
            report.add("order_status", False, f"{type(exc).__name__}: {exc}")

    return report
