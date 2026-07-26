"""Al Ostedh Action Provider adapter — a REAL restaurant-backend integration.

Maps Ordy's platform tools onto the *Al Ostedh Fast Food Platform* REST API
(Express 5 + Prisma + PostgreSQL). Ordy's ``create_order`` becomes ``POST /api/orders`` on
the customer's authenticated session; ``get_order_status`` reads the order back.

The adapter is **config-driven**: the endpoints come from an ``ordy.config.json`` Capability
Map (produced by ``@ordy/analyze`` and approved by the owner), not from hardcoded paths — so
the same adapter follows the restaurant's real routes. It depends only on the ``RestTransport``
protocol (one generic ``request``), so it is fully unit-testable with a fake and driven by
httpx in production (see ``scripts/demo_alostedh.py``). No model ever reaches this code — by
the time ``execute`` runs, the action is already validated, priced and confirmed by the gate.

Two impedance mismatches with Ordy's domain are handled here, explicitly:

* **Money.** Al Ostedh stores prices as float TND; Ordy works in integer *millimes*
  (TND exponent = 3, doc 06 §1). Conversion goes through ``to_minor`` using ``Decimal`` so
  a value like ``13.9`` never picks up binary-float noise (``13900``, not ``13900.0000002``).

* **Idempotency.** The Al Ostedh API has no idempotency support (a retried ``POST /orders``
  creates a second order — one of the gaps Ordy's gate exists to close). The adapter sends an
  ``Idempotency-Key`` (forward-compatible if the backend ever honors it) AND keeps a
  per-instance replay cache so a retried ``execute()`` returns the first result instead of
  double-creating. True end-to-end idempotency still needs server support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from ordy_core.money import exponent

from ordy_tools.pricing import ProductSnapshot
from ordy_tools.providers.config_loader import OrdyConfig, RouteBinding

# Ordy order ``type`` → Al Ostedh ``deliveryMode``. Al Ostedh has no dine-in, so anything
# that isn't a delivery is treated as pickup (à emporter).
_DELIVERY_MODE = {"delivery": "DELIVERY", "pickup": "PICKUP", "dine_in": "PICKUP"}

# Sane defaults if no config is supplied — the routes @ordy/analyze detects for Al Ostedh.
_DEFAULT_ROUTES: dict[str, RouteBinding] = {
    "create_order": RouteBinding("create_order", "POST", "/api/orders", True, 0.95),
    "get_order_status": RouteBinding("get_order_status", "GET", "/api/orders/:id", True, 0.75),
}


def to_minor(major: float | str, currency: str = "TND") -> int:
    """Convert a major-unit amount (e.g. float TND from Al Ostedh) to integer minor units."""
    exp = exponent(currency)
    return int((Decimal(str(major)) * (10**exp)).to_integral_value())


def to_major(minor: int, currency: str = "TND") -> str:
    """Inverse of :func:`to_minor` — a decimal string suitable for an amount field."""
    exp = exponent(currency)
    if exp == 0:
        return str(minor)
    quantum = Decimal(1).scaleb(-exp)  # e.g. 0.001 for TND
    return str((Decimal(minor) / (10**exp)).quantize(quantum))


class RestTransport(Protocol):
    """A minimal HTTP transport. httpx in prod; a fake in tests."""

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        auth: bool = False,
        idempotency_key: str | None = None,
    ) -> dict: ...


@dataclass(slots=True)
class CustomerContext:
    """Order fields that come from the customer/session, NOT from the model.

    Ordy's ``create_order`` tool args carry only *what* to order (type + items); *who* it is
    for — name, phone, address, payment choice — is resolved from the authenticated session
    and passed here. Keeping it out of the model's tool args is deliberate: the model can
    never redirect an order to a different phone or address.
    """

    contact_name: str
    contact_phone: str
    payment_method: str = "CASH"  # CASH | FLOUCI | STRIPE
    shipping_address: str | None = None
    shipping_city: str | None = None


class AlOstedhAdapter:
    """Executes Ordy actions against the live Al Ostedh backend (doc 01 §4.8, doc 07 §6)."""

    name = "alostedh"

    def __init__(
        self,
        transport: RestTransport,
        customer: CustomerContext,
        *,
        routes: dict[str, RouteBinding] | None = None,
        currency: str = "TND",
    ) -> None:
        self._t = transport
        self._customer = customer
        self._routes = {**_DEFAULT_ROUTES, **(routes or {})}
        self._currency = currency
        self._seen: dict[str, dict] = {}

    async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
        if idempotency_key in self._seen:  # replay within this process → never double-create
            return self._seen[idempotency_key]

        if tool_key == "create_order":
            result = await self._create_order(args, idempotency_key)
        elif tool_key == "get_order_status":
            b = self._routes["get_order_status"]
            raw = await self._t.request(
                b.method, _fill(b.path, str(args.get("order_ref", ""))), auth=b.auth_required
            )
            result = {"status": _map_status(raw.get("status"))}
        else:
            # cancel_order etc.: no customer-facing endpoint. Raising lets FallbackAdapter
            # degrade to the native store rather than silently dropping.
            raise NotImplementedError(f"Al Ostedh provider does not map tool '{tool_key}'")

        self._seen[idempotency_key] = result
        return result

    async def _create_order(self, args: dict, idempotency_key: str) -> dict:
        b = self._routes["create_order"]
        payload = self._order_payload(args)
        raw = await self._t.request(
            b.method, b.path, json=payload, auth=b.auth_required, idempotency_key=idempotency_key
        )
        # Al Ostedh returns the created Order row (201). Its `status` is a KITCHEN status;
        # acceptance of the order maps to Ordy's "confirmed".
        return {
            "order_id": str(raw.get("id", "")),
            "status": "confirmed",
            "total_minor": to_minor(raw.get("totalAmount", 0), self._currency),
            "currency": self._currency,
        }

    def _order_payload(self, args: dict) -> dict:
        order_type = str(args.get("type", "pickup"))
        delivery_mode = _DELIVERY_MODE.get(order_type, "PICKUP")
        items = [
            {
                "productId": str(it.get("product_id")),
                "quantity": int(it.get("quantity", 1)),
                **({"customizationNotes": it["note"]} if it.get("note") else {}),
            }
            for it in args.get("items", [])
        ]
        payload: dict = {
            "items": items,
            "deliveryMode": delivery_mode,
            "contactName": self._customer.contact_name,
            "contactPhone": self._customer.contact_phone,
            "paymentMethod": self._customer.payment_method,
        }
        if delivery_mode == "DELIVERY":
            if self._customer.shipping_address:
                payload["shippingAddress"] = self._customer.shipping_address
            if self._customer.shipping_city:
                payload["shippingCity"] = self._customer.shipping_city
        if args.get("note"):
            payload["notes"] = args["note"]
        if args.get("scheduled_for"):
            payload["scheduledAt"] = args["scheduled_for"]
        return payload


def adapter_from_config(
    config: OrdyConfig, transport: RestTransport, customer: CustomerContext
) -> AlOstedhAdapter:
    """Build a ready-to-execute adapter from an approved ordy.config.json.

    Enforces consent: a config the owner never approved cannot drive order placement.
    """
    config.require_consent()
    return AlOstedhAdapter(transport, customer, routes=config.routes, currency=config.currency)


def _fill(path: str, ref: str) -> str:
    """Substitute a path parameter (``:id`` or ``{id}``) with ``ref``; append if none."""
    if ":" in path or "{" in path:
        return re.sub(r"(:\w+|\{\w+\})", ref, path, count=1)
    return f"{path.rstrip('/')}/{ref}" if ref else path


# Al Ostedh kitchen status → a coarse Ordy-facing status string.
_STATUS_MAP = {
    "PENDING": "confirmed",
    "PREPARING": "preparing",
    "READY": "ready",
    "DELIVERED": "delivered",
}


def _map_status(raw: str | None) -> str:
    return _STATUS_MAP.get(str(raw or "").upper(), "unknown")


def menu_snapshot(products: list[dict], *, currency: str = "TND") -> dict[str, ProductSnapshot]:
    """Build Ordy's priced menu snapshot from ``GET /api/products``.

    This is the snapshot the policy engine prices against — so the total the customer
    confirms is derived here, from the restaurant's own catalog, never from the model.
    Al Ostedh products are flat (no variants/modifiers), so each maps to a single price.
    """
    snapshot: dict[str, ProductSnapshot] = {}
    for p in products:
        pid = str(p.get("id", ""))
        if not pid:
            continue
        snapshot[pid] = ProductSnapshot(
            product_id=pid,
            name=str(p.get("name", "")),
            currency=currency,
            price_minor=to_minor(p.get("price", 0), currency),
            is_available=bool(p.get("isAvailable", True)),
        )
    return snapshot
