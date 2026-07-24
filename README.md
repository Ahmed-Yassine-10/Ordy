# Ordy

**The AI waiter that understands, talks, and takes action.**

Ordy is an API-first, autonomous AI voice agent platform for restaurants. Customers hold natural voice conversations — in English, French, or Tunisian Derja — to order food, book tables, check availability, and get answers. Restaurants connect their website, database, POS, API, or repository; Ordy learns their menu, hours, and policies, then acts on their systems through a secure, audited tool-execution layer.

> **Status: Phase 4 — Knowledge base + RAG (in progress).** Phase 1 (architecture) is complete under [docs/](docs/). Phase 2 delivered auth, tenancy, and menu on **PostgreSQL Row-Level Security from the first migration** ([docs/PHASE-2.md](docs/PHASE-2.md)); Phase 3 the restaurant-intelligence pipeline (URL → reviewed menu draft + capability map, [docs/PHASE-3.md](docs/PHASE-3.md)). Phase 4 adds retrieval — `ordy-rag` (heading-aware chunking, embeddings behind a port, hybrid vector+FTS search with RRF fusion, grounding checks), `knowledge_chunks` on pgvector (HNSW), embed-at-publish (searchable iff approved), and a retrieval search API + debug UI with provenance ([docs/PHASE-4.md](docs/PHASE-4.md)).

## The one rule that shapes everything

The LLM never touches a database, an API, or a browser directly.

```
Conversation → Understanding → Planning → Validation → Action → Confirmation

        LLM ──► Intent + Tool Call ──► Policy Engine ──► Validation Layer
                                                              │
        Restaurant System ◄── Secure Executor ◄───────────────┘
```

Every state-changing operation passes through a typed tool schema, a deterministic policy engine, a validation layer, and an audited executor. The model proposes; the platform disposes.

## Documentation index

| Doc | Contents |
|---|---|
| [01 — System Architecture](docs/01-architecture.md) | Topology, every component explained, core data flows, deployment model |
| [02 — Technical Decisions](docs/02-technical-decisions.md) | 15 ADRs: stack choices, trade-offs, and their consequences |
| [03 — Agent Engine](docs/03-agent-engine.md) | LangGraph orchestration, the five agents, tool/action framework, AI safety |
| [04 — Ingestion Pipeline](docs/04-ingestion.md) | Restaurant intelligence: crawl → extract → capability map → human review |
| [05 — Voice Architecture](docs/05-voice.md) | Real-time audio, dual pipeline modes, latency budgets, Derja strategy |
| [06 — Database Schema](docs/06-database-schema.md) | Full PostgreSQL schema, multi-tenancy via RLS, partitioning, pgvector |
| [07 — API Specification](docs/07-api-spec.md) | REST resources, WebSocket voice protocol, webhooks, Action Provider spec |
| [08 — Security](docs/08-security.md) | Threat model, tenant isolation, AI safety controls, sandbox spec, GDPR/PCI posture |
| [09 — Repository Structure](docs/09-repo-structure.md) | Monorepo layout, package boundaries, codegen, CI |
| [10 — Roadmap](docs/10-roadmap.md) | 10 phases with deliverables, exit criteria, and de-risking spikes |

## Stack at a glance

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 |
| Agent runtime | LangGraph (supervisor graph over five specialized agents) |
| LLM | OpenAI models behind a provider-agnostic model router |
| Voice | LiveKit (WebRTC/SIP transport) + dual pipeline: realtime speech-to-speech and Deepgram STT → agent → streaming TTS |
| Data | PostgreSQL 16 (+ pgvector), Redis, S3-compatible object storage |
| Jobs | Celery workers (ingestion, sync, webhooks) + isolated Playwright automation runners |
| Infra | Docker Compose (dev) → Kubernetes (prod), OpenTelemetry + Langfuse observability |

## Repository layout (planned)

```
ordy/
├── apps/web/              # Next.js — restaurant dashboard, admin panel, widget host
├── services/api/          # FastAPI — core API + agent orchestration (modular monolith)
├── services/voice/        # Voice gateway — LiveKit agent workers, telephony bridge
├── services/workers/      # Celery — ingestion, sync, webhook delivery
├── services/automation/   # Sandboxed Playwright runners (isolated deployable)
├── packages/              # TS: generated SDK, embeddable widget, shared UI
├── libs/                  # Python: ordy-core, ordy-ai, ordy-tools, ordy-security
├── infra/                 # docker/, k8s/, terraform/
├── evals/                 # Agent quality & red-team suites
└── docs/                  # You are here
```

Full rationale in [09 — Repository Structure](docs/09-repo-structure.md).
