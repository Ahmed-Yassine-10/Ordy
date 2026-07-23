# 07 — API Specification

The human-readable contract for Ordy's APIs. Once code exists, the FastAPI-generated OpenAPI document is authoritative and this doc becomes narrative; until then, this is the source. Four surfaces: **Platform REST API** (`/v1`), **Public customer API** (`/v1/public`), **realtime channels** (LiveKit + WebSockets), and **outbound** (webhooks + the Action Provider spec).

## 1. Conventions

- **Base**: `https://api.ordy.ai/v1`. Versioning in the path; additive changes don't bump; breaking changes ship as `/v2` with overlap.
- **Auth**: `Authorization: Bearer <jwt>` (dashboard users) or `X-Api-Key: ordy_live_…` (machines). Public endpoints use short-lived session tokens. Every authenticated request resolves to `(principal, restaurant_id, scopes)` → RLS context.
- **Content**: JSON, `snake_case`, timestamps RFC 3339 UTC, money as `{amount_minor, currency}`.
- **Errors**: RFC 7807 `application/problem+json`:

```json
{
  "type": "https://docs.ordy.ai/errors/validation-rejected",
  "title": "Action rejected by validation",
  "status": 422,
  "code": "ORDER_BELOW_DELIVERY_MINIMUM",
  "detail": "Delivery orders require a minimum of 25.000 TND; cart total is 18.500 TND.",
  "instance": "req_01J9…",
  "meta": {"minimum_minor": 25000, "cart_minor": 18500}
}
```

- **Idempotency**: all POSTs accept `Idempotency-Key`; replays return the original result with `Idempotent-Replay: true`.
- **Pagination**: cursor-based — `?limit=50&cursor=…` → `{data: [...], next_cursor}`.
- **Rate limits**: token bucket per API key / user / IP; `429` + `Retry-After`; headers `X-RateLimit-Limit/Remaining/Reset` on every response.
- **Scopes** (API keys): `orders:read|write`, `reservations:read|write`, `menu:read|write`, `knowledge:read|write`, `conversations:read`, `webhooks:manage`, `agent:manage`.

## 2. Platform REST API

### 2.1 Auth & identity

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Email+password signup → verification email |
| POST | `/auth/login` | → `{access_token, expires_in}` + httpOnly refresh cookie |
| POST | `/auth/refresh` | Rotate refresh, new access token |
| POST | `/auth/logout` | Revoke refresh token family |
| GET/POST | `/auth/oauth/google/start` · `/callback` | OAuth code flow |
| GET/PATCH | `/me` | Profile, locale, password change (re-auth required) |

### 2.2 Restaurants, members, keys

| Method | Path | Purpose |
|---|---|---|
| POST | `/restaurants` | Create tenant (creator becomes `owner`) |
| GET/PATCH | `/restaurants/{id}` | Settings, hours config, languages, `voice_enabled` switch |
| GET/PUT | `/restaurants/{id}/hours` | Operating hours per service type |
| GET/POST/PATCH/DELETE | `/restaurants/{id}/members[/{user_id}]` | Invites + RBAC roles |
| GET/POST/DELETE | `/restaurants/{id}/api-keys[/{key_id}]` | Key lifecycle; secret returned once on create |

### 2.3 Knowledge & ingestion

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/restaurants/{id}/sources` | Register website / DB / GitHub / API-doc / upload source |
| POST | `/sources/{id}/runs` | Trigger ingestion run |
| GET | `/runs/{id}` | Live stage status + stats (dashboard polls or subscribes §4.2) |
| GET | `/runs/{id}/review` | The review payload: drafts + provenance + diffs |
| POST | `/runs/{id}/review` | `{approvals: [...], edits: [...], rejections: [...]}` → publish |
| GET/PATCH | `/restaurants/{id}/documents[/{doc_id}]` | Browse/edit knowledge docs |
| POST | `/restaurants/{id}/knowledge/search` | Debug retrieval: `{query, language}` → chunks + scores + provenance |

### 2.4 Menu

Full CRUD: `/restaurants/{id}/menus`, `/menus/{id}/categories`, `/restaurants/{id}/products[/{product_id}]`, nested `variants`, `modifier-groups`, `modifiers`. Highlights:

| Method | Path | Purpose |
|---|---|---|
| POST | `/menus/{id}/publish` | Draft → published (atomic version bump; re-embeds affected knowledge) |
| POST | `/products/{id}/availability` | Fast 86 switch: `{is_available: false}` — takes effect on the very next agent turn |

### 2.5 Capability & tools

| Method | Path | Purpose |
|---|---|---|
| GET | `/restaurants/{id}/capability-maps` · `/{version}` | Draft + active maps, diff view |
| POST | `/capability-maps/{id}/approve` | Compile approved entries → `restaurant_tools` |
| GET | `/tools/catalog` | Platform ToolSpec catalog (schemas included) |
| GET/PUT | `/restaurants/{id}/tools[/{tool_key}]` | Enable/disable, adapter binding, caps (tighten-only), channels |
| GET | `/restaurants/{id}/workflows[/{wf_id}]` | Browser workflows + verification status |
| POST | `/workflows/{id}/verify` | Trigger sandbox dry-run; response includes artifact links |

### 2.6 Agent config & sandbox

| Method | Path | Purpose |
|---|---|---|
| GET/PATCH | `/restaurants/{id}/agent-config` | Persona, voice, languages, escalation, model overrides |
| POST | `/restaurants/{id}/sandbox/conversations` | Start a **text sandbox** conversation (full pipeline, `NativeAdapter` forced, marked `sandbox`) |
| POST | `/sandbox/conversations/{id}/turns` | Send a customer utterance → full agent response + trace (plan, validation report) for inspection |

### 2.7 Conversations, orders, reservations

| Method | Path | Purpose |
|---|---|---|
| GET | `/restaurants/{id}/conversations` | Filterable list (status, outcome, channel, date) |
| GET | `/conversations/{id}` | Detail: turns, actions with validation reports, audio links, metrics |
| POST | `/conversations/{id}/takeover` | Staff joins: agent yields, dashboard chat relay |
| GET/PATCH | `/restaurants/{id}/orders[/{order_id}]` | List/feed; staff status transitions (`confirmed→preparing→ready→completed`) |
| POST | `/restaurants/{id}/orders` | Manual order entry (dashboard/API) — same validation pipeline, no confirmation gate |
| GET/PATCH/POST | `/restaurants/{id}/reservations[…]` | Calendar list, status transitions, manual creation |

### 2.8 Webhooks, billing, admin

| Method | Path | Purpose |
|---|---|---|
| GET/POST/PATCH/DELETE | `/restaurants/{id}/webhooks[/{id}]` | Endpoints + subscribed events; `POST …/test` sends a signed ping |
| GET | `/restaurants/{id}/usage` | Metered usage by metric/period (billing transparency) |
| GET/POST | `/restaurants/{id}/billing/…` | Stripe portal session, plan changes |
| GET | `/admin/…` | Platform-admin: tenants, runs, usage rollups, flags, audit search (separate RBAC + `app.role`) |

## 3. Public customer API (`/v1/public`)

Unauthenticated-but-protected surface consumed by the widget and hosted page. Protections: per-IP+session rate limits, bot challenge (Turnstile-class) on session creation, short-lived tokens, origin allowlist per tenant.

| Method | Path | Purpose |
|---|---|---|
| GET | `/public/restaurants/{slug}/bootstrap` | Branding, languages, greeting, open-now, text-mode availability |
| POST | `/public/restaurants/{slug}/voice-sessions` | → `{conversation_id, livekit: {url, token}, session_token, expires_in}` |
| POST | `/public/restaurants/{slug}/text-sessions` | → `{conversation_id, ws_url, session_token}` (text fallback / accessibility) |
| GET | `/public/orders/{tracking_token}` | Customer order-status page (token from confirmation SMS) |

## 4. Realtime channels

### 4.1 Customer session — audio via LiveKit, events via data channel / WS

Audio flows through LiveKit (doc 05). Structured events ride the LiveKit data channel (voice) or the session WebSocket (text mode). Same message catalog both ways:

**Server → client**

```jsonc
{"type": "session.ready",       "conversation_id": "cnv_…", "language": "fr", "mode": "voice"}
{"type": "agent.state",         "state": "listening" | "thinking" | "speaking" | "executing"}
{"type": "transcript.partial",  "role": "customer", "text": "je veux une piz"}
{"type": "transcript.final",    "role": "customer", "turn": 7, "text": "Je veux une pizza pepperoni grande"}
{"type": "transcript.final",    "role": "agent",    "turn": 8, "text": "Très bon choix ! …"}
{"type": "cart.updated",        "cart": {"items": [...], "total": {"amount_minor": 32000, "currency": "TND"}}}
{"type": "action.confirmation_request",
   "action_id": "act_…",
   "summary": "1× Pizza Pepperoni (grande) — à emporter — total 32.000 TND",
   "expires_in": 120}
{"type": "action.result",       "action_id": "act_…", "status": "succeeded",
   "kind": "order", "ref": "A1042", "eta_minutes": 20}
{"type": "session.error",       "code": "STT_DEGRADED", "recoverable": true}
{"type": "session.end",         "reason": "completed" | "abandoned" | "handoff"}
```

**Client → server**

```jsonc
{"type": "text.message",          "text": "une pizza margherita"}        // text mode / accessibility
{"type": "confirmation.response", "action_id": "act_…", "approved": true} // tap-to-confirm parallels voice "yes"
{"type": "control.mute", "muted": true}
{"type": "session.close"}
```

Contract notes: confirmation can arrive by voice **or** UI tap — first one wins, both are logged with origin. `cart.updated` lets the widget render a live cart the customer can *see* while talking — trust-building for voice ordering.

### 4.2 Dashboard live feed — `WS /v1/restaurants/{id}/live`

JWT-authenticated. Server pushes: `order.created|updated`, `reservation.created|updated`, `conversation.started|ended|handoff_requested`, `ingestion.run_progress`, `workflow.verification_result`. Used by the live order feed, handoff inbox, and onboarding progress UI.

## 5. Outbound webhooks

Signed events to restaurant systems (`webhook_endpoints`):

**Catalog**: `order.created`, `order.confirmed`, `order.status_changed`, `order.cancelled`, `reservation.created`, `reservation.updated`, `reservation.cancelled`, `conversation.completed`, `conversation.handoff_requested`, `knowledge.change_pending_review`, `workflow.degraded`, `usage.threshold_reached`.

**Envelope + signature**:

```
POST {endpoint.url}
Ordy-Event: order.created
Ordy-Delivery: whd_01J9…
Ordy-Timestamp: 1784841600
Ordy-Signature: v1=hex(hmac_sha256(secret, timestamp + "." + body))
```

```json
{"id": "evt_01J9…", "type": "order.created", "created_at": "2026-07-23T18:00:00Z",
 "restaurant_id": "res_01J8…", "data": {"order": { "…": "full order object" }}}
```

Verification: reject if `|now − timestamp| > 300 s` or signature mismatch. Retries: exponential backoff (1 m → 5 m → 30 m → 2 h → 6 h), then `dead` + dashboard notification; auto-disable after 20 consecutive failures.

## 6. Action Provider spec (restaurant-implemented interface)

The inversion that makes Ordy API-first from the restaurant's side too: a restaurant (or its POS middleware) can implement this small interface and get **native execution** with zero browser automation. Ingestion detects it from an OpenAPI doc; conformance is verified automatically; the `RestAdapter` binds to it.

Auth: Ordy sends `Authorization: Bearer <provider_token>` (per-tenant secret held in the vault). All bodies JSON.

| Method | Path (restaurant's base URL) | Purpose | Required? |
|---|---|---|---|
| GET | `/ordy/menu` | Full menu in Ordy schema (items, variants, modifiers, availability) — enables continuous sync | ✔ |
| GET | `/ordy/availability?product_ref=…` | Real-time availability/stock | optional (falls back to menu) |
| POST | `/ordy/orders` | Create order; must honor `Idempotency-Key` header; → `{ref, status, eta_minutes}` | ✔ for order execution |
| GET | `/ordy/orders/{ref}` | Order status | ✔ if orders |
| POST | `/ordy/orders/{ref}/cancel` | Cancellation (compensation hook) | recommended |
| GET | `/ordy/reservations/slots?date=…&party_size=…` | Bookable slots | ✔ for reservations |
| POST | `/ordy/reservations` | Create reservation (idempotent) | ✔ for reservations |

Conformance runner (`POST /v1/restaurants/{id}/tools/conformance`): exercises the provider with synthetic data in a marked test mode (`Ordy-Test: true`), validates schemas/idempotency/latency, and gates enabling the `rest` adapter — a failed conformance run cannot be bound to live tools.

## 7. Error code catalog (domain layer)

Stable `code` values carried in problem+json and in validation reports — the same codes the Conversation agent receives for graceful repair:

`TOOL_NOT_ENABLED` · `SCHEMA_INVALID` · `PRODUCT_NOT_FOUND` · `PRODUCT_UNAVAILABLE` · `VARIANT_REQUIRED` · `MODIFIER_RULE_VIOLATION` · `OUTSIDE_OPERATING_HOURS` · `OUTSIDE_DELIVERY_ZONE` · `ORDER_BELOW_DELIVERY_MINIMUM` · `ORDER_ABOVE_CAP` · `QUANTITY_ABOVE_CAP` · `RATE_LIMITED_CUSTOMER` · `CONFIRMATION_EXPIRED` · `CONFIRMATION_MISSING` · `RESERVATION_SLOT_UNAVAILABLE` · `PARTY_SIZE_EXCEEDED` · `ADAPTER_UNAVAILABLE` · `EXECUTION_FAILED_FELL_BACK` · `PROMOTION_INVALID`
