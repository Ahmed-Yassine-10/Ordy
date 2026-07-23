# Phase 2 — Auth + SaaS dashboard foundation

Status of the Phase 2 build (roadmap [doc 10](10-roadmap.md)). Goal: a deployable
skeleton with real auth, tenancy, and the dashboard shell — with tenant isolation
(RLS) enforced from the very first migration.

## What's implemented

**Monorepo & infra**
- uv (Python) + pnpm (TS) workspaces; shared `ruff`/`mypy`/`pytest` config.
- `docker compose` dev stack: Postgres (pgvector), Redis, MinIO, LiveKit (voice profile), the API.
- `initdb/01-roles.sql` provisions `ordy_app` (no BYPASSRLS) and `ordy_migrator` (owner, BYPASSRLS) — the isolation invariant depends on the app never connecting as an owner role.
- GitHub Actions CI: ruff + migrate + unit/RLS-isolation tests (with a Postgres service) + web typecheck/build.

**`libs/ordy-core`** — domain foundation
- UUIDv7 keys, exponent-aware `Money` (TND = 3 minor digits), enums, error hierarchy + codes.
- SQLAlchemy 2.0 models: identity/tenancy (`users`, `oauth_accounts`, `refresh_tokens`, `restaurants`, `restaurant_members`, `api_keys`) and menu (`menus`, `menu_categories`, `products`, `product_variants`, `modifier_groups`, `modifiers`).
- `Database` + `TenantContext` + `apply_tenant_context` — the RLS mechanism: transaction-local GUCs (`app.user_id`, `app.restaurant_id`, `app.is_platform_admin`) set via `set_config(..., true)` (PgBouncer-safe).

**`libs/ordy-security`** — Argon2id passwords, JWT access tokens, opaque hashed refresh tokens (rotation + reuse detection), scoped API-key generation/verification.

**`services/api`** — FastAPI modular monolith
- App factory, request-ID middleware, CORS, RFC 7807 problem+json error mapping.
- Dependency layer (`deps.py`): principal resolution (JWT / API key) → tenant context → RLS-scoped session; `require_tenant(min_role)` authorizes the path's restaurant and pins the tenant GUC.
- Modules: `auth` (register/login/refresh/logout/me), `restaurants` (create/list/get/update, members invite/list), `menu` (categories, products, variants, availability).
- Alembic `0001_initial`: builds the schema from ORM metadata, then layers the **RLS policies + SECURITY DEFINER helpers** (`app_is_member`, `app_api_key_candidates`).
- `seed_demo.py` — "Pizza Rustica Sfax" with an owner and a menu.
- `tests/test_tenant_isolation.py` — the cross-tenant isolation gate.

**`apps/web`** — Next.js dashboard shell: landing, login, and a "your restaurants" page wired to the API through a thin client (to be replaced by the generated SDK).

## How the RLS design works (the important part)

Two-variable model. `app.user_id` is set for every authenticated request, enabling
"my memberships" policies on `restaurant_members` and membership-based visibility on
`restaurants` (via the `SECURITY DEFINER` `app_is_member()` helper, which is owned by
the BYPASSRLS migrator so it doesn't recurse into RLS). `app.restaurant_id` is set
only *after* `require_tenant` has authorized membership, and it drives the simple
`restaurant_id = app_current_restaurant()` policy on every tenant table. All policies
are `FORCE`d, so even the table owner is subject to them; only the migrator's
BYPASSRLS attribute (used by helper functions) steps around them, deliberately.

Identity tables (`users`, `oauth_accounts`, `refresh_tokens`) carry no tenant RLS —
auth lookups (login by email, token refresh) must run before any tenant context
exists; access is mediated in the app layer.

## Run it locally

```bash
cp .env.example .env                      # then set a real JWT_SECRET
docker compose up --build                 # Postgres, Redis, MinIO, api
# in another shell:
cd services/api && uv run alembic upgrade head
uv run python -m ordy_api.scripts.seed_demo
# API at http://localhost:8000  (OpenAPI docs at /docs)
cd ../../apps/web && pnpm install && pnpm dev   # dashboard at http://localhost:3000
```

Demo login: `owner@pizzarustica.tn` / `demo-password-123`.

## Remaining for Phase 2 exit criteria

- [ ] Google OAuth flow (register/login by password is done).
- [ ] API-key management endpoints (verification path + model/RLS are done).
- [ ] SDK codegen job (`packages/sdk` from `/openapi.json`) wired into CI.
- [ ] Stripe subscription skeleton (trial plan).
- [ ] Run the isolation suite green in CI against the ephemeral Postgres (workflow is in place).
- [ ] Dashboard: settings, member management UI, manual menu manager screens.

## Validation done in this environment

Python was syntax-checked (`compileall`) across all packages and the `Money`/UUIDv7
logic was smoke-tested (uuid7 version bits verified). The stack itself (migrations,
RLS behavior, HTTP flows, the web build) has **not** been run here — no
Docker/Postgres/uv/pnpm in the authoring environment. First real run happens on a
machine with the toolchain; the CI workflow is the reference for a clean bring-up.
