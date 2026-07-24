"""Execution adapters beyond native (doc 01 §4.8, doc 07 §6).

``RestAdapter`` speaks the Action Provider interface a restaurant implements.
``FallbackAdapter`` composes primary+fallback so an integration outage degrades to
Ordy's own store instead of losing the order — the promise that makes integrations safe
to enable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ordy_tools.executor import ExecutorAdapter


class ProviderClient(Protocol):
    """Transport to the restaurant's Action Provider. HTTP in prod; fake in tests."""

    async def post(self, path: str, payload: dict, *, idempotency_key: str) -> dict: ...
    async def get(self, path: str, params: dict | None = None) -> dict: ...


class ProviderError(RuntimeError):
    """Raised by a client when the provider is unreachable or returns an error."""


class RestAdapter:
    """Maps platform tools onto the Action Provider endpoints (doc 07 §6)."""

    name = "rest"

    def __init__(self, client: ProviderClient) -> None:
        self._client = client

    async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
        if tool_key == "create_order":
            raw = await self._client.post("/ordy/orders", args, idempotency_key=idempotency_key)
            return {
                "order_id": str(raw.get("ref", "")),
                "status": raw.get("status", "confirmed"),
                "eta_minutes": raw.get("eta_minutes"),
            }
        if tool_key == "make_reservation":
            raw = await self._client.post("/ordy/reservations", args, idempotency_key=idempotency_key)
            return {"reservation_id": str(raw.get("ref", "")), "status": raw.get("status", "confirmed")}
        if tool_key == "cancel_order":
            await self._client.post(
                f"/ordy/orders/{args.get('order_ref')}/cancel", args, idempotency_key=idempotency_key
            )
            return {"cancelled": True}
        if tool_key == "get_order_status":
            raw = await self._client.get(f"/ordy/orders/{args.get('order_ref')}")
            return {"status": raw.get("status", "unknown")}
        if tool_key == "check_availability":
            raw = await self._client.get("/ordy/availability", {"product_ref": args.get("product_id")})
            return {"available": bool(raw.get("available", True))}
        raise ProviderError(f"tool '{tool_key}' is not mapped to the Action Provider")


class FallbackAdapter:
    """Try the primary adapter; on failure fall back and notify. Orders are never lost."""

    def __init__(
        self,
        primary: ExecutorAdapter,
        fallback: ExecutorAdapter,
        *,
        on_fallback: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._on_fallback = on_fallback
        self.name = primary.name
        self.used_fallback = False

    async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
        try:
            result = await self._primary.execute(tool_key, args, idempotency_key=idempotency_key)
            self.used_fallback = False
            self.name = self._primary.name
            return result
        except Exception as exc:  # noqa: BLE001 — any primary failure degrades, never drops
            self.used_fallback = True
            self.name = self._fallback.name
            if self._on_fallback:
                self._on_fallback(tool_key, exc)
            return await self._fallback.execute(tool_key, args, idempotency_key=idempotency_key)
