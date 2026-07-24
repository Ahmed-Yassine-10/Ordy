# Phase 6 — Tool-calling framework (the action gate)

Status of the Phase 6 build (roadmap [doc 10](10-roadmap.md)). This is the architectural
heart of Ordy: **the deterministic gate between model output and real side effects**
(ADR-010). It ships before any real execution exists — Phase 7 swaps the executor's body
for real orders; the gate does not change.

## The invariant, in code

```
model proposes a tool call
   ↓ whitelist ......... tenant-enabled? channel allowed?
   ↓ schema ............ typed args, bounds, enums
   ↓ referential ....... product/variant exists, belongs here, is available
   ↓ PRICING ........... totals computed from the menu; model totals DISCARDED
   ↓ business rules .... open hours, delivery zone, delivery minimum
   ↓ caps .............. per-item qty, item count, order value, action budget
   ↓ confirmation ...... explicit, recent yes to a SYSTEM-GENERATED summary
   ↓ execute ........... idempotent, adapter-isolated, output-schema validated
   ↓ audit ............. append-only action_executions with the full report
```

Every step is a code branch. The model cannot raise caps, enable tools, alter prices, or
skip confirmation: those live in tables it cannot address and branches it cannot reach.

## What's implemented

**`libs/ordy-tools`** — the gate, pure and provider-free:
- `catalog.py` — the platform ToolSpec catalog (create_order, check_availability,
  make_reservation, cancel_order, get_order_status, request_human_handoff). Tools ship via
  code review; `manifest()` exposes only enabled tools to the model.
- `policy.py` — the ordered, fail-fast pipeline with named validators, `Caps` that tenants
  may only **tighten**, and `build_summary()` (the confirmation text, spoken verbatim).
- `pricing.py` — **server-side pricing**. The model picks items; the system prices them.
- `schema.py` — `SchemaValidator` port: a built-in subset validator (keeps the gate
  testable with zero deps) or the `jsonschema` library in production.
- `confirm.py` — the confirmation gate with **two independent staleness guards**
  (wall-clock TTL *and* conversational distance) and `interpret_response` where anything
  ambiguous is **not** consent.
- `executor.py` — idempotency, adapter isolation, output-schema validation, `NativeAdapter`
  (synthetic results in Phase 6; real orders in Phase 7 behind the same contract).

**`libs/ordy-agent`** — the action path: `plan_actions` (deliberately conservative — an
unresolved size is left empty so the gate *asks* rather than the brain guessing), the
confirmation interrupt across turns, and rejection codes rendered as conversational repair.

**Data** — migration `0005`: `tool_definitions` (GLOBAL, **seeded from code** so the DB can
never hold a tool the code doesn't implement), `restaurant_tools` (the tenant whitelist,
with who approved it), `action_executions` (append-only audit) — the tenant tables under
the usual FORCE'd RLS.

**API** — `GET /tools` + `PUT /tools/{key}` (enable/caps/channels, manager+), a DB-backed
`PolicyContext` builder (bindings, published-menu snapshot, hours, delivery, caps), and the
sandbox now runs the full gate and persists the action audit.

**Frontend** — a Tools page (risk badges, enable/disable, caps) and the sandbox where an
order proposal shows the priced summary and waits for a yes.

## Validation done in this environment

**50 unit tests pass** across the repo (Python 3.13, stdlib) — including the **21-test
action-gate + red-team suite**, all blocked by a *deterministic layer*, never by model
politeness:

| Attack | Blocked by |
|---|---|
| Model claims a 100% discount / a fake total | Unknown properties rejected; pricing reads only the menu |
| Calls a tool that doesn't exist (`grant_discount`) | Not in the catalog; absent from the manifest |
| Calls a tool the tenant disabled / wrong channel | `TOOL_NOT_ENABLED` / `CHANNEL_NOT_ALLOWED` |
| Orders another restaurant's product id | `PRODUCT_NOT_FOUND` (not in this tenant's snapshot) |
| 999 pizzas | Schema bound, then `QUANTITY_ABOVE_CAP` independently |
| Tenant config tries to *raise* a platform cap | `tightened_by` — caps only tighten |
| "yes" 8 turns later / 200s later | `CONFIRMATION_EXPIRED` (both guards) |
| Ambiguous reply treated as consent | `interpret_response` → `None` → gate stays closed |
| Adapter returns malformed output | `OutputSchemaViolation` |

Plus 7 end-to-end agent action tests: an order proposal is server-priced (`32.000 TND`),
confirmation executes exactly once (idempotent), declining executes nothing, a missing size
is repaired not guessed, and read-only mode still never proposes actions.

**Not executed here** (no Postgres): migration 0005 + catalog seeding, the DB-backed
PolicyContext, and action-audit persistence — syntax-validated only; CI + `docker compose`
are the reference.

## Remaining / deferred

- LLM planner (structured output on the PLANNING tier) — the rule-based planner backs dev/CI;
  either way the gate is identical.
- Real `NativeAdapter` writing orders/reservations (Phase 7), plus `operating_hours` /
  `delivery_zones` tables (hours + delivery currently come from `restaurants.settings`).
- Compensation execution (specs declare it; the executor runs it in Phase 7 with real state).
- Multi-step plans (max 5 steps designed; Phase 6 executes the first step per turn).
