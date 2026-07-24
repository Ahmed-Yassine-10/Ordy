# Phase 7 — Order execution 🎯 (sellable milestone)

Status of the Phase 7 build (roadmap [doc 10](10-roadmap.md)). Confirmed plans become
**real orders and reservations**. This is the commercial wedge: a restaurant with nothing
but a menu gets a working agent whose orders land in the Ordy dashboard — no integration
required.

## What's implemented

**`libs/ordy-orders`** (new, pure) — the order domain, unit-testable without a DB:
- **`state.py`** — order + reservation state machines. Staff, agent, and API all go through
  the *same* rules; terminal states are final; `next_states()` drives the dashboard buttons.
- **`hours.py`** — timezone-aware opening hours, including **windows that span midnight**
  (19:00→02:00 stays open into the next day) — the case naive implementations get wrong and
  a late-night restaurant lives in.
- **`zones.py`** — delivery zones by radius (haversine) or polygon (ray casting); the
  **cheapest** matching zone wins so overlaps behave predictably.
- **`totals.py`** — integer-minor-unit totals; discounts clamped so a promotion can never
  produce a negative or free order.

**`libs/ordy-tools`** additions:
- **`RestAdapter`** — the Action Provider client (doc 07 §6).
- **`FallbackAdapter`** — primary→fallback composition: **an integration outage degrades to
  Ordy's own store instead of losing the order**, with a notification hook.
- **`execute_plan` + `compensate`** — a failed later step rolls back completed ones.
- **`conformance.py`** — the Action Provider conformance runner. The decisive check is
  idempotency: a provider that creates a second order on replay **fails** and cannot be
  bound to live tools.

**`ordy-core`** — `webhooks.py`: canonical-JSON envelope, HMAC signature over
`timestamp.body` (replay-resistant), constant-time verification, and the retry ladder
(1m→5m→30m→2h→6h→dead-letter).

**Data** — migration `0006`: customers, orders, order_items, order_events, reservations,
operating_hours, delivery_zones, webhook_endpoints, webhook_deliveries, usage_records — all
under the same FORCE'd per-tenant RLS.

**API** — `DbNativeAdapter` (the Phase 7 body behind Phase 6's unchanged contract) writes
real orders with snapshotted line items, an event timeline, a tracking token, and
idempotent replay; the orders/reservations API with **state-machine-enforced** transitions;
and the policy context now reads **real operating hours and delivery zones**.

**Frontend** — a live operations feed: orders with status badges, line items, totals, and
only the valid next-step buttons.

## Validation done in this environment

**80 unit tests pass** across the repo (Python 3.13, stdlib) — 30 new in Phase 7:

- **State machine**: happy path, illegal jumps rejected (`draft→completed`,
  `confirmed→ready`), terminal states final, reservation paths.
- **Hours**: open/closed inside and outside windows, **midnight-spanning window open at
  01:00 and closed at 03:00**, per-service isolation.
- **Zones**: radius + polygon matching, cheapest-overlap wins, inactive zones never match,
  haversine sanity.
- **Totals**: delivery fee added; percent promo respects minimum; **an oversized/injected
  discount is clamped — never negative, never free**.
- **Execution**: RestAdapter mapping, **idempotent replay creates one order**, **fallback to
  native when the provider is down** (order captured, ops notified), **compensation rolls
  back the created order when a later step fails**.
- **Conformance**: a conformant provider passes; a **non-idempotent provider fails** with a
  precise reason; a dead provider fails.
- **Webhooks**: signature round-trip, tamper and wrong-secret detection, **replay outside
  the 5-minute tolerance rejected**, canonical JSON, retry ladder terminates.

**Not executed here** (no Postgres): migration 0006, `DbNativeAdapter` writes, the orders
API, and the policy context's hours/zone queries — syntax-validated only. CI +
`docker compose` are the reference.

## Remaining / deferred

- **SMS confirmations + the unauthenticated public tracking page** (needs Twilio; the
  tracking endpoint exists but is tenant-scoped for now).
- **Webhook delivery worker** — signing, envelope, and retry policy are done and tested;
  the Celery dispatch loop + endpoint CRUD land with the events pipeline.
- **Stripe billing + plan limits**; usage metering has its table but no writers yet.
- **Live WebSocket feed** — the dashboard polls every 10s today.
- **50-concurrent load test** and the end-to-end pilot demo (both need a live stack).
- Address-based zone matching at order time (the cheapest active zone's terms apply until
  an address is captured).
