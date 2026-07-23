"""Capability analysis (doc 04 §2.5, §3).

Turns an OpenAPI document into REST capability candidates, then assembles the
Capability Map — every platform action gets an entry, with the restaurant's own API
(``rest``) used where detected and Ordy's ``native`` store as the always-available
capability/fallback (doc 01 §4.8).
"""

from __future__ import annotations

from ordy_ingest.models import CapabilityCandidate

# Ordy's native order/reservation store can back all of these, so every action is at
# least native-feasible. A detected REST endpoint upgrades the binding.
PLATFORM_ACTIONS = [
    "create_order",
    "update_order",
    "cancel_order",
    "get_order_status",
    "check_availability",
    "make_reservation",
    "cancel_reservation",
    "check_reservation_slots",
    "request_human_handoff",
    "send_payment_link",
    "log_customer_preference",
]

# Actions that only ever run against Ordy's own systems — never a restaurant endpoint.
_ALWAYS_NATIVE = {"request_human_handoff", "send_payment_link", "log_customer_preference"}


def _haystack(path: str, method: str, op: dict) -> str:
    parts = [path, method, str(op.get("operationId", "")), str(op.get("summary", ""))]
    parts += [str(t) for t in op.get("tags", [])]
    return " ".join(parts).lower()


def _match_action(path: str, method: str, op: dict) -> tuple[str, float] | None:
    h = _haystack(path, method, op)
    m = method.lower()
    has = lambda *words: any(w in h for w in words)  # noqa: E731

    order = has("order")
    reservation = has("reservation", "booking", "reserve", "table")
    cancel = has("cancel", "void")
    availability = has("availab", "stock", "inventory", "in-stock")
    slots = has("slot", "availab", "opening")

    if order and cancel and m in {"post", "delete"}:
        return "cancel_order", 0.85
    if order and m in {"put", "patch"}:
        return "update_order", 0.8
    if order and m == "post":
        return "create_order", 0.85
    if order and m == "get":
        return "get_order_status", 0.8
    if reservation and cancel and m in {"post", "delete"}:
        return "cancel_reservation", 0.85
    if reservation and slots and m == "get":
        return "check_reservation_slots", 0.8
    if reservation and m == "post":
        return "make_reservation", 0.85
    if availability and m == "get":
        return "check_availability", 0.8
    return None


def analyze_openapi(spec: dict) -> list[CapabilityCandidate]:
    """Best REST candidate per action, extracted from an OpenAPI 3 document."""
    best: dict[str, CapabilityCandidate] = {}
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"} or not isinstance(op, dict):
                continue
            matched = _match_action(path, method, op)
            if matched is None:
                continue
            action, confidence = matched
            if action in _ALWAYS_NATIVE:
                continue
            candidate = CapabilityCandidate(
                action=action,
                feasible=True,
                adapter="rest",
                confidence=confidence,
                binding={"method": method.upper(), "path": path, "operation_id": op.get("operationId")},
                evidence=[{"kind": "openapi_operation", "path": path, "method": method.upper()}],
            )
            if action not in best or confidence > best[action].confidence:
                best[action] = candidate
    return list(best.values())


def build_capability_map(
    candidates: list[CapabilityCandidate],
    *,
    coverage: dict,
    version: int = 1,
) -> dict:
    """Assemble the versioned Capability Map (doc 04 §3)."""
    by_action = {c.action: c for c in candidates if c.feasible}
    capabilities: list[dict] = []
    for action in PLATFORM_ACTIONS:
        rest = by_action.get(action)
        if rest is not None:
            capabilities.append({
                "action": action,
                "feasible": True,
                "adapter": "rest",
                "confidence": rest.confidence,
                "binding": rest.binding,
                "evidence": rest.evidence,
            })
        else:
            capabilities.append({
                "action": action,
                "feasible": True,
                "adapter": "native",
                "confidence": 1.0,
                "binding": {"source": "ordy_native"},
            })
    return {
        "capability_map_version": "1.0",
        "version": version,
        "status": "draft",
        "capabilities": capabilities,
        "knowledge": coverage,
    }
