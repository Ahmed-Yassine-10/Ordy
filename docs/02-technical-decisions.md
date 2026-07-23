# 02 — Technical Decisions (ADRs)

Fifteen architecture decision records. Format: **Context → Decision → Alternatives considered → Consequences**. Statuses are `accepted` unless marked. Decisions marked ⚠ deviate from the original brief, with rationale.

---

## ADR-001 — Monorepo

**Context.** One small team building a frontend, four backend services, shared Python libs, and a generated TS SDK that must never drift from the API contract.

**Decision.** Single monorepo: pnpm workspaces for TS, uv workspaces for Python, shared CI.

**Alternatives.** Polyrepo (per service): version-skew hell for a team of this size; contract drift between API and SDK becomes a standing bug source.

**Consequences.** Atomic cross-stack changes (API + SDK + dashboard in one PR); one CI pipeline with path-filtered jobs; requires discipline on package boundaries (enforced by import-linting, doc 09).

---

## ADR-002 — Modular monolith API; separate deployables only for voice, workers, automation

**Context.** The brief lists many backend capabilities (gateway, auth, restaurant management, orchestration, knowledge, execution). Deploying each as a microservice multiplies ops cost for a startup and adds network hops inside the latency-critical agent loop.

**Decision.** One FastAPI deployable (`services/api`) containing auth, domain modules, the agent orchestrator, and the tool executor — organized as vertical modules with enforced import boundaries. Separate deployables only where the runtime profile differs physically: `voice` (long-lived audio sessions), `workers` (bursty batch), `automation` (untrusted code execution).

**Alternatives.** Full microservices: rejected — premature; the modules share one database and one domain model. Everything-in-one including voice: rejected — audio workers pin memory/CPU for minutes and need independent scaling and draining.

**Consequences.** One API to version and deploy; agent-to-domain calls are in-process function calls (fast, transactional). The orchestrator ships as `libs/ordy-agent`, so extracting it into its own service later is a packaging change, not a rewrite. Risk: monolith modules entangling — mitigated by import-linter contracts in CI.

---

## ADR-003 — Python/FastAPI backend, Next.js frontend, OpenAPI-generated TS SDK

**Context.** Brief recommends FastAPI + Next.js. The AI ecosystem (LangGraph, LiveKit Agents, Playwright, ingestion tooling) is Python-first.

**Decision.** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic. Next.js App Router + TypeScript + Tailwind. The OpenAPI spec is the contract: `packages/sdk` is generated in CI; hand-editing it is forbidden.

**Alternatives.** Node/NestJS backend: weaker AI library support. tRPC: couples frontend to a TS backend we don't have.

**Consequences.** Two languages is a real cost, paid deliberately for the AI ecosystem. Contract-first discipline means backend changes surface as typed diffs in the frontend.

---

## ADR-004 — LangGraph for agent orchestration

**Context.** The agent loop is a stateful, cyclic, multi-role workflow (converse ↔ retrieve ↔ plan → validate → execute → confirm) needing durable state, interruption (human confirmation), and replayability.

**Decision.** LangGraph `StateGraph` with a supervisor routing among five roles (doc 03). Checkpointing to Postgres; `interrupt` used for customer-confirmation gates.

**Alternatives.** Hand-rolled loop: we'd reinvent checkpointing/interrupts badly. CrewAI/AutoGen: optimized for autonomous multi-agent collaboration, weaker at the deterministic control flow and hard validation gates we require. LlamaIndex Workflows: retrieval remains LlamaIndex-friendly, but graph control in LangGraph is stronger.

**Consequences.** Graph state is inspectable per turn (great for eval + conversation replay); framework lock-in is contained — nodes are plain functions over a typed state, portable if needed.

---

## ADR-005 ⚠ — pgvector first; dedicated vector DB behind a port

**Context.** Brief recommends Qdrant/Pinecone. Ordy's corpora are *small*: a restaurant's knowledge base is hundreds of chunks, not millions. The operational cost of a second stateful store (backup, tenancy, consistency with approvals) is the dominant factor at this scale.

**Decision.** pgvector (HNSW) inside the primary Postgres, with tenant filtering in SQL under the same RLS as everything else. All retrieval goes through a `VectorStore` port; a Qdrant adapter is the planned escape hatch when a tenant's corpus or platform-wide QPS outgrows Postgres.

**Alternatives.** Qdrant now: better ANN at scale we don't have; costs an extra store + sync between "approved" state in PG and vectors elsewhere. Pinecone: managed, but data residency + per-namespace cost model fits poorly with thousands of tiny tenants.

**Consequences.** One database to operate, transactional consistency between approval state and searchability (a chunk is searchable *iff* approved — same commit). Revisit trigger: retrieval p95 > 100 ms or corpus > ~5M chunks platform-wide.

---

## ADR-006 — Redis + Celery for jobs; Redis Streams for events

**Context.** Ingestion crawls, embedding jobs, webhook delivery, scheduled re-syncs: retryable, observable background work. Live dashboards need event fan-out.

**Decision.** Celery (Redis broker) with dedicated queues (`ingestion`, `embeddings`, `webhooks`, `automation-dispatch`); beat for schedules. Redis Streams + consumer groups for domain events feeding dashboard WS and webhook workers.

**Alternatives.** ARQ/Dramatiq: lighter, but Celery's retry semantics, routing, and monitoring maturity win for production. Kafka: absurd overkill at this stage; Streams gives ordered fan-out with zero new infra.

**Consequences.** Redis becomes critical infra (HA in prod). Workers must set tenant context exactly like request handlers (RLS discipline extends to jobs).

---

## ADR-007 — Multi-tenancy: shared schema + PostgreSQL Row-Level Security

**Context.** Thousands of small tenants; strong isolation demanded; per-tenant databases are operationally untenable at this size.

**Decision.** Single database, shared schema, `restaurant_id UUID NOT NULL` on every tenant table, RLS policies keyed to `current_setting('app.restaurant_id')`. The app role cannot bypass RLS; a separate migration/admin role can. Middleware (and every Celery task entrypoint) sets the setting inside the transaction. CI runs an isolation test suite that attempts cross-tenant reads on every table.

**Alternatives.** Schema-per-tenant: migration fan-out nightmare. App-layer filtering only: one forgotten `WHERE` = breach.

**Consequences.** Defense in depth (app filter + RLS); slight per-query overhead (acceptable); connection pooling must use `SET LOCAL` semantics to avoid context bleed (PgBouncer transaction mode compatible).

---

## ADR-008 — Provider-agnostic model router; OpenAI as launch default

**Context.** Model quality/price shifts quarterly; voice needs a realtime speech model; extraction wants a cheap structured-output model; the brief recommends OpenAI.

**Decision.** A `ModelRouter` port with named tiers — `REALTIME_SPEECH`, `CONVERSATION`, `PLANNING`, `EXTRACTION`, `CLASSIFIER`, `EMBEDDING` — mapped to concrete provider+model IDs in config (env/DB), per-tenant overridable. Launch mapping: OpenAI across tiers. No literal model ID in application code. All calls logged with tokens + latency + cost to usage metering.

**Alternatives.** Direct SDK calls with hardcoded models: every model deprecation becomes a code change. LiteLLM-style proxy: attractive; may be adopted *inside* the router later without changing the port.

**Consequences.** Model upgrades and A/B tests are config; multi-provider fallback (e.g., on provider outage) becomes possible; per-tier cost attribution is native.

---

## ADR-009 — Voice: LiveKit transport + dual pipeline (realtime S2S / modular STT→TTS)

**Context.** Requirements: sub-second latency, barge-in, phone + web, and **Tunisian Derja** — which realtime speech-to-speech models handle poorly today, while a modular pipeline lets us pick the best Arabic-capable STT and control code-switching.

**Decision.** LiveKit as the only audio transport (WebRTC for web, Twilio SIP → LiveKit for phone). `services/voice` workers run either **Mode A** (realtime speech-to-speech API, EN/FR default) or **Mode B** (streaming STT → agent → streaming TTS; required for Derja), selected per language/tenant. Both modes drive the *same* orchestrator. Vendor choices inside Mode B (Deepgram vs Whisper-family for Derja; ElevenLabs vs Azure for Arabic TTS) are resolved by the Phase 5 benchmark spike, not assumed.

**Alternatives.** Raw WebSocket audio to our servers: we'd rebuild jitter buffers, echo cancellation, SIP bridging — LiveKit's solved problems. Twilio-only stack: locks voice to telephony; web widget is our primary channel.

**Consequences.** One new infra dependency (self-host or LiveKit Cloud — decided in the spike by ops cost); barge-in/VAD/turn-detection largely handled by the agents framework; Derja quality is a benchmarked choice with a fallback ladder (doc 05 §6).

---

## ADR-010 — Tool execution security model (the core invariant)

**Context.** The defining risk of an agentic platform: model output causing unintended side effects (prompt injection, hallucinated parameters, over-ordering).

**Decision.** Every side effect flows through the pipeline: **typed ToolSpec (JSON Schema) → tenant whitelist check → schema validation → deterministic policy engine (business rules, caps, hours, availability) → customer confirmation gate for state-changing actions → idempotent executor via adapter → outcome validation → append-only audit record**. The LLM's only power is emitting a tool call; tools are registered by the platform and enabled per tenant by a human. No dynamic tool creation at conversation time. Retrieved content (web pages, menus, KB chunks) is structurally marked untrusted and can never introduce instructions or tools (doc 08 §6).

**Alternatives.** "LLM with DB credentials and guidelines": categorically rejected; it is the failure mode this product exists to avoid.

**Consequences.** Every action is explainable (validation report stored), replayable (audit), and bounded (caps). Latency cost of validation is microseconds — it's in-process code. New restaurant capabilities require registering tools, which is exactly the friction we want.

---

## ADR-011 — Browser automation: sandboxed, human-verified, payment-free

**Context.** Long-tail restaurants have only a website. AI-generated browser workflows are powerful and dangerous (site changes, destructive clicks, secret exposure).

**Decision.** Workflows are *generated* by AI during onboarding, *verified* by dry-run + human approval, then *executed* deterministically (no model in the execution loop) by Playwright in hardened containers: non-root, read-only FS, egress allow-listed to the target domain, per-run credentials scoped and injected at runtime, every step screenshotted + DOM-snapshotted to object storage. The agent **never enters payment card data**; flows end at cash-on-pickup/delivery or a payment link. A workflow that drifts (selector failure) auto-disables its tool → executor falls back to `NativeAdapter` + staff notification.

**Alternatives.** LLM-driven browsing at order time ("computer use"): unbounded latency and risk per order; rejected for execution (retained as an option for *workflow generation* during onboarding, where a human reviews the output).

**Consequences.** Deterministic, auditable execution; a maintenance loop (selector drift) that is monitored, not silent; strict blast-radius containment (doc 08 §5).

---

## ADR-012 — Ingestion requires human approval before publish

**Context.** Extraction will sometimes misread prices, merge items, or hallucinate. A wrong price spoken confidently by a voice agent is a trust-destroying event.

**Decision.** Ingestion output lands as **drafts** with per-fact provenance (source URL, snippet, timestamp, extractor confidence). The dashboard review step is mandatory before first publish. Subsequent re-syncs auto-approve only *non-substantive* changes; price/availability changes always queue for review (one-tap approve). Every published fact keeps its provenance for "why did the agent say that?" debugging.

**Alternatives.** Auto-publish with confidence thresholds: confidence scores are not calibrated enough to bet the restaurant's pricing on.

**Consequences.** Onboarding has a human step (minutes, not hours — the UI is built for skim-and-approve); the agent's knowledge is defensibly correct; provenance doubles as the injection-quarantine boundary (doc 08 §6).

---

## ADR-013 — Identity: JWT + refresh rotation for humans; hashed scoped API keys for machines; customers are phone-identified

**Context.** Three principal types: restaurant staff (dashboard), machines (API/SDK), and end customers (who will never create an account to order a pizza).

**Decision.** Staff: email/password + Google OAuth → short-lived JWT access (15 min) + rotating refresh tokens (httpOnly cookie for web), RBAC roles `owner|manager|staff|viewer` per restaurant membership. Machines: API keys (`ordy_live_…`), stored as SHA-256 hashes, prefix-searchable, scoped and revocable. Customers: identified per-tenant by phone number (verified via the call itself or OTP for web when needed); no passwords; consent-gated memory.

**Alternatives.** Auth0/Clerk: viable, but auth is core to a security-critical platform and the RBAC/RLS coupling is easier first-party; revisit if SSO/enterprise demands grow.

**Consequences.** Standard, boring auth (good); customer PII minimized by design; API keys never recoverable post-creation.

---

## ADR-014 — Observability: OpenTelemetry + Langfuse + per-tenant metering from day one

**Context.** An agent platform is undebuggable without traces ("why did it say that?") and unpriceable without per-tenant cost data (LLM + audio margins).

**Decision.** OTel tracing across widget → API → graph nodes → tool executions → adapters, with conversation/turn IDs as correlation keys. Langfuse (self-hosted) for LLM spans, prompt versions, and eval runs. Every model/STT/TTS call writes a `usage_records` row (tenant, metric, quantity, cost) — the same table drives billing and margin dashboards. PII redaction at the log/trace boundary.

**Alternatives.** LangSmith: strong, but self-hostable Langfuse fits data-control posture. "Add observability later": later is when you need it and don't have it.

**Consequences.** Cost of ~5% overhead instrumentation; conversation replay becomes a first-class debugging and eval asset.

---

## ADR-015 — Payments: PCI scope avoidance; Stripe for SaaS billing only

**Context.** Handling card data in-conversation (voice!) would drag the platform into PCI-DSS scope and voice-phishing risk.

**Decision.** v1 order payments: cash on pickup/delivery, or a Stripe Payment Link / restaurant-hosted checkout URL sent by SMS — the agent never sees a PAN, ever, in any channel. Ordy's own subscription billing: Stripe Billing with usage-based metering from `usage_records`.

**Alternatives.** In-conversation card capture via DTMF masking: real tech, real cost, not a v1 differentiator.

**Consequences.** Fast, safe launch; "pay by card on the phone" is a documented non-feature until a tokenized flow justifies itself.

---

## Decision summary table

| # | Decision | Reversibility |
|---|---|---|
| 001 | Monorepo | Cheap to split later |
| 002 | Modular monolith + 3 satellite services | Extraction path prepared |
| 003 | FastAPI + Next.js + generated SDK | Foundational |
| 004 | LangGraph orchestration | Nodes portable |
| 005 | pgvector behind a port ⚠ | Swap = adapter |
| 006 | Celery + Redis Streams | Standard |
| 007 | Shared schema + RLS | Foundational |
| 008 | Model router, OpenAI default | Config-level swap |
| 009 | LiveKit + dual voice pipeline | Spike-validated |
| 010 | Tool execution invariant | **Non-negotiable** |
| 011 | Sandboxed, verified, payment-free automation | **Non-negotiable** |
| 012 | Human approval before publish | Non-negotiable for prices |
| 013 | JWT/API keys/phone identity | Standard |
| 014 | OTel + Langfuse + metering day-one | Foundational |
| 015 | PCI avoidance | Revisit post-v1 |
