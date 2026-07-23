# 09 — Repository Structure

One monorepo (ADR-001): pnpm workspaces for TypeScript, uv workspaces for Python, path-filtered CI. This doc is the map; scaffolding happens at the start of Phase 2.

## 1. Tree

```
ordy/
├── apps/
│   └── web/                          # Next.js App Router (TypeScript, Tailwind)
│       ├── src/app/
│       │   ├── (dashboard)/          # restaurant-facing routes
│       │   │   ├── onboarding/      #   wizard: source → run progress → review → approve
│       │   │   ├── knowledge/       #   documents, provenance, re-sync, diffs
│       │   │   ├── menu/            #   menu manager, publish, 86 switches
│       │   │   ├── agent/           #   persona/voice config + text sandbox
│       │   │   ├── operations/      #   live orders, reservations, handoff inbox
│       │   │   ├── conversations/   #   transcripts, audio playback, action traces
│       │   │   └── settings/        #   members, api keys, webhooks, tools, billing
│       │   ├── (admin)/              # platform admin panel
│       │   └── (widget)/             # hosted customer page  order.ordy.ai/{slug}
│       └── src/{components,lib,hooks}/
│
├── services/
│   ├── api/                          # FastAPI modular monolith (ADR-002)
│   │   ├── src/ordy_api/
│   │   │   ├── main.py               # app factory, middleware chain, router mount
│   │   │   ├── modules/              # VERTICAL modules — routes/service/repo per domain
│   │   │   │   ├── auth/  restaurants/  menu/  knowledge/  capability/
│   │   │   │   ├── conversations/  orders/  reservations/  agent/
│   │   │   │   ├── actions/          # tool registry, policy engine, executors, adapters
│   │   │   │   ├── webhooks/  billing/  admin/  public/
│   │   │   ├── middleware/           # request-id, auth, tenant-context (RLS), rate-limit, audit
│   │   │   └── events/               # Redis Streams publishers/consumers
│   │   ├── alembic/                  # migrations (source of truth: doc 06)
│   │   └── tests/
│   │
│   ├── voice/                        # LiveKit agent workers (doc 05)
│   │   ├── src/ordy_voice/
│   │   │   ├── worker.py             # room lifecycle, session state
│   │   │   ├── pipelines/            # mode_a_realtime.py · mode_b_modular.py
│   │   │   ├── stt/  tts/            # vendor adapters behind SpeechPipeline ports
│   │   │   ├── turns.py              # endpointing, barge-in, back-channel logic
│   │   │   └── telephony/            # Twilio SIP bridge config (phase 5.5+)
│   │   └── tests/
│   │
│   ├── workers/                      # Celery app (queues: ingestion, embeddings, webhooks, schedules)
│   │   ├── src/ordy_workers/
│   │   │   ├── ingestion/            # discover.py crawl.py parse.py extract.py synthesize.py publish.py monitor.py
│   │   │   ├── analysis/             # openapi.py repo_static.py db_introspect.py flow_trace.py
│   │   │   ├── embeddings.py  webhooks.py  metering.py  beat_schedules.py
│   │   └── tests/
│   │
│   └── automation/                   # Playwright sandbox runner (separate image, doc 08 §5)
│       ├── src/ordy_automation/
│       │   ├── runner.py             # deterministic workflow replay + assertions
│       │   ├── generator/            # onboarding-time trace → workflow compile (LLM-assisted)
│       │   ├── artifacts.py          # screenshots/DOM capture with field masking
│       └── tests/
│
├── libs/                             # Python shared libraries (uv workspace members)
│   ├── ordy-core/                    #   domain models (Pydantic), DB models (SQLAlchemy), money/time/i18n utils, errors
│   ├── ordy-agent/                   #   the LangGraph graph, state, nodes, prompts/ (versioned), model router
│   ├── ordy-tools/                   #   ToolSpec types, platform tool catalog, validators, adapter interfaces
│   ├── ordy-rag/                     #   chunking, embedding, hybrid retrieval, VectorStore port (pgvector impl)
│   └── ordy-security/                #   auth primitives, vault/envelope encryption, redaction, rate limiting
│
├── packages/                         # TypeScript shared (pnpm workspace members)
│   ├── sdk/                          #   GENERATED API client from OpenAPI — never hand-edited
│   ├── widget/                       #   embeddable voice widget (script-tag bundle, LiveKit client, cart UI)
│   ├── ui/                           #   shared components/design tokens (dashboard + widget)
│   └── config/                       #   shared tsconfig/eslint/tailwind presets
│
├── evals/                            # agent quality (doc 03 §9) — run in CI + on demand
│   ├── conversations/                #   golden multi-turn scenarios per language
│   ├── toolcalls/                    #   utterance → expected-plan pairs
│   ├── redteam/                      #   injection & abuse suites (must be blocked deterministically)
│   └── runner/                       #   harness: replay, LLM-judge rubrics, report diffing
│
├── infra/
│   ├── docker/                       # Dockerfiles per service + docker-compose.yml (full local stack)
│   ├── k8s/                          # Kustomize/Helm: base + overlays (staging, prod), NetworkPolicies, runtime classes
│   └── terraform/                    # cloud: VPC, managed PG/Redis, object storage, KMS, DNS, LiveKit infra
│
├── docs/                             # this documentation set (01–10)
├── scripts/                          # seed_demo.py, gen_sdk.ps1/sh, dev bootstrap
├── .github/workflows/                # CI pipelines (path-filtered)
├── pnpm-workspace.yaml  package.json # TS workspace root
├── pyproject.toml  uv.lock           # uv workspace root (members: services/*, libs/*)
└── docker-compose.yml → infra/docker/
```

## 2. Boundary rules (enforced, not aspirational)

- **Python**: import-linter contracts in CI —
  `libs/ordy-core` imports nothing internal · `ordy-agent`/`ordy-tools`/`ordy-rag` may import `ordy-core` only · `services/*` may import `libs/*`; **no service imports another service** · `modules/*` inside the API may import siblings only via their `service.py` facade (no reaching into another module's `repo.py`).
- **TypeScript**: `apps/web` consumes the API exclusively through `packages/sdk`; raw `fetch` to `/v1` is lint-banned outside the SDK.
- **The executor rule**: only `services/api/modules/actions` (and the automation runner it dispatches) may touch external restaurant systems. Grep-able, reviewable, auditable.

## 3. Codegen flow

```
FastAPI app → openapi.json (CI artifact)
           → openapi-typescript / orval → packages/sdk (typed client + zod schemas)
           → CI fails if generated output differs from committed SDK (drift gate)
```

Same job publishes the spec to the docs site later. ToolSpec JSON Schemas live in `libs/ordy-tools` and are the single source for: model function manifests, validation, SDK action types, and doc rendering.

## 4. Tooling & conventions

| Concern | Choice |
|---|---|
| Python | 3.12, uv (workspace, lock), ruff (lint+format), mypy (strict in `libs/`), pytest + pytest-asyncio |
| TypeScript | pnpm, TS strict, ESLint + Prettier, Vitest, Playwright (E2E for dashboard) |
| Task runner | `just` (cross-platform; Windows-friendly) — `just dev`, `just test`, `just gen-sdk`, `just seed` |
| Commits/PRs | Conventional commits; PR template with security-touch checklist; CODEOWNERS per top-level dir |
| Config | 12-factor env vars; `.env.example` per service; pydantic-settings typed config objects; zero secrets in repo (gitleaks CI) |

## 5. CI (path-filtered, one workflow file per concern)

1. **lint-test** — ruff/mypy/pytest + eslint/vitest, filtered by changed paths.
2. **contract** — regenerate OpenAPI + SDK, fail on drift; ToolSpec schema validation.
3. **security** — pip/pnpm audit, semgrep, gitleaks, trivy on images; **RLS isolation suite** against an ephemeral Postgres.
4. **evals** — tool-call accuracy + red-team suites on `libs/ordy-agent` or `prompts/` changes (budgeted model usage; full golden suite nightly).
5. **e2e** — compose up the stack, seed demo tenant, run dashboard + text-sandbox E2E.
6. **build-publish** — images per service on main, tagged by SHA; deploy via overlay bump (Phase 10 automates).

## 6. Local development

`docker compose up` brings up: Postgres (+pgvector), Redis, MinIO, LiveKit dev server, api, voice, workers, automation (profile-gated), web — with hot reload mounted for api/web. `just seed` creates the demo restaurant ("Pizza Rustica Sfax") with a published menu, enabled native tools, and a sandbox conversation ready in the dashboard. A developer should go from clone to talking to the demo agent (text sandbox) in under 15 minutes; that number is a tracked DX metric, not a hope.
