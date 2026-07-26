"""End-to-end demo: place a REAL order on the live Al Ostedh backend THROUGH Ordy's gate.

This is not a mock. It talks to https://al-ostedh-api.vercel.app, pulls the real menu, and
drives one order through the full deterministic action gate:

    whitelist → schema → server-side pricing → business rules → caps
      → deterministic confirmation → idempotent execute → audit

The endpoints are taken from an approved ordy.config.json when one is present (the artifact
@ordy/analyze emits), proving the whole loop: analyze → config → adapter → live order.

Run:
    pip install httpx
    PYTHONPATH="libs/ordy-core/src;libs/ordy-tools/src" python scripts/demo_alostedh.py

Env:
    ALOSTEDH_API    base URL (default https://al-ostedh-api.vercel.app)
    ORDY_CONFIG     path to an ordy.config.json (endpoints + consent). Optional.
    ALOSTEDH_EMAIL / ALOSTEDH_PASSWORD   reuse a customer; otherwise a throwaway is registered
    DEMO_PLACE_ORDER=0   dry-run: stop right before the real POST
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx

# Windows consoles default to cp1252 and choke on the arrows/checkmarks below.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from ordy_tools.adapters import FallbackAdapter
from ordy_tools.catalog import CREATE_ORDER
from ordy_tools.confirm import (
    ConfirmationState,
    interpret_response,
    request_confirmation,
    resolve_confirmation,
)
from ordy_tools.executor import NativeAdapter, execute_action
from ordy_tools.models import ActionStatus
from ordy_tools.policy import PolicyContext, ToolBinding, validate_action
from ordy_tools.providers.alostedh import (
    AlOstedhAdapter,
    CustomerContext,
    adapter_from_config,
    menu_snapshot,
    to_major,
)
from ordy_tools.providers.config_loader import load_config

API = os.environ.get("ALOSTEDH_API", "https://al-ostedh-api.vercel.app").rstrip("/")
PLACE = os.environ.get("DEMO_PLACE_ORDER", "1") != "0"
CONFIG_PATH = os.environ.get("ORDY_CONFIG")


def banner(step: str, title: str) -> None:
    print(f"\n\033[1m[{step}]\033[0m \033[36m{title}\033[0m")


class HttpxTransport:
    """A RestTransport backed by httpx — adds the bearer token and Idempotency-Key header."""

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        self._c = client
        self._token = token

    async def request(self, method, path, *, json=None, params=None, auth=False, idempotency_key=None) -> dict:
        headers = {}
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        r = await self._c.request(method, f"{API}{path}", json=json, params=params, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} → {r.status_code}: {r.text[:200]}")
        return r.json()


async def authenticate(client: httpx.AsyncClient) -> tuple[str, CustomerContext]:
    email = os.environ.get("ALOSTEDH_EMAIL")
    password = os.environ.get("ALOSTEDH_PASSWORD")
    if email and password:
        r = await client.post(f"{API}/api/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        user = r.json()["user"]
        name = f"{user.get('firstName', '')} {user.get('lastName', '')}".strip()
        return r.json()["token"], CustomerContext(name or "Ordy Demo", "+21620123456", payment_method="CASH")

    email = f"ordy-demo+{uuid.uuid4().hex[:10]}@example.com"
    body = {"email": email, "password": "OrdyDemo123!", "firstName": "Ordy", "lastName": "Demo", "phone": "+21620123456"}
    r = await client.post(f"{API}/api/auth/register", json=body)
    r.raise_for_status()
    print(f"    registered throwaway customer: {email}")
    return r.json()["token"], CustomerContext("Ordy Demo", "+21620123456", payment_method="CASH")


def build_adapter(transport, customer):
    """Build from an approved ordy.config.json if given, else the built-in Al Ostedh defaults."""
    if CONFIG_PATH:
        cfg = load_config(CONFIG_PATH)
        print(f"    using ordy.config.json for '{cfg.restaurant_name}' (approved by {cfg.consent_by})")
        return adapter_from_config(cfg, transport, customer)
    return AlOstedhAdapter(transport, customer)


async def main() -> int:
    print(f"\033[1mOrdy → Al Ostedh live integration demo\033[0m  ({API})")
    async with httpx.AsyncClient(timeout=30) as client:
        banner("0", "Authenticate + pull the real menu")
        token, customer = await authenticate(client)
        transport = HttpxTransport(client, token)
        products = await transport.request("GET", "/api/products")
        available = [p for p in products if p.get("isAvailable")]
        print(f"    {len(products)} products, {len(available)} available")
        menu = menu_snapshot(products)

        picks = available[:2]
        if len(picks) < 2:
            print("    not enough available products to demo"); return 1
        for p in picks:
            print(f"      • {p['name']}  {to_major(menu[p['id']].price_minor)} TND")

        banner("1", "Model output — items chosen, NOTHING priced by the model")
        model_args = {
            "type": "pickup",
            "items": [
                {"product_id": picks[0]["id"], "quantity": 2},
                {"product_id": picks[1]["id"], "quantity": 1, "note": "extra sauce"},
            ],
        }
        print(f"    create_order args: {model_args}")
        print("    (a compromised client claimed total = 0.001 TND — the gate never reads it)")

        banner("2", "Policy gate — whitelist · schema · server-side pricing · caps")
        ctx = PolicyContext(
            channel="text_widget",
            currency="TND",
            bindings={"create_order": ToolBinding("create_order", enabled=True, adapter="alostedh")},
            menu=menu,
            service_open={"pickup": True, "delivery": True, "dine_in": True},
        )
        report = validate_action(CREATE_ORDER, model_args, ctx)
        for c in report.checks:
            mark = "\033[32m✓\033[0m" if c.passed else "\033[31m✗\033[0m"
            print(f"      {mark} {c.name}" + (f"  → {c.code}" if not c.passed else ""))
        if not report.passed:
            print(f"    REJECTED: {report.human_message}"); return 1
        print(f"    server-computed total: \033[1m{to_major(report.total_minor)} TND\033[0m")

        banner("3", "Confirmation gate — explicit + fresh, or it does not execute")
        now = datetime.now(UTC)
        conf = request_confirmation(
            action_id=str(uuid.uuid4()), tool_key="create_order",
            summary=report.summary, args=model_args, now=now, turn_seq=1,
        )
        print(f"    assistant says: “{report.summary}. C'est bon pour toi ?”")
        for reply in ("euh je sais pas", "oui, vas-y"):
            verdict = interpret_response(reply)
            label = {True: "APPROVE", False: "DECLINE", None: "UNCLEAR → not consent"}[verdict]
            print(f"      customer: “{reply}”  → {label}")
        state = resolve_confirmation(conf, approved=True, now=now + timedelta(seconds=8), current_turn_seq=2)
        print(f"    confirmation state: \033[1m{state.value}\033[0m")
        if state is not ConfirmationState.CONFIRMED:
            print("    not confirmed — nothing placed."); return 1

        if not PLACE:
            print("\n\033[33mDRY RUN (DEMO_PLACE_ORDER=0) — stopping before the real order.\033[0m")
            return 0

        banner("4", "Execute — real POST, config-driven path, fallback + idempotency")
        adapter = FallbackAdapter(
            build_adapter(transport, customer),
            NativeAdapter(),
            on_fallback=lambda tool, exc: print(f"      ! primary failed ({exc}); fell back to native"),
        )
        idem = conf.action_id
        outcome = await execute_action(CREATE_ORDER, model_args, adapter, idempotency_key=idem)
        print(f"    status={outcome.status.value}  adapter={outcome.adapter}  ref={outcome.external_ref}")
        if outcome.status is not ActionStatus.SUCCEEDED:
            print(f"    FAILED: {outcome.error}"); return 1

        again = await execute_action(CREATE_ORDER, model_args, adapter, idempotency_key=idem)
        print(f"    replay with same key → ref={again.external_ref} (same order, no double-charge)")

        banner("5", "Verify — read the order back from Al Ostedh")
        if outcome.adapter == "alostedh":
            row = await transport.request("GET", f"/api/orders/{outcome.external_ref}", auth=True)
            print(f"    GET /api/orders/{outcome.external_ref}")
            print(f"      total={row.get('totalAmount')} TND  status={row.get('status')}  "
                  f"mode={row.get('deliveryMode')}  items={len(row.get('items', []))}")
            print("\n\033[32m✓ Real order placed on Al Ostedh, end-to-end, through Ordy's gate.\033[0m")
        else:
            print("    order captured in Ordy's native store (primary was down).")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
