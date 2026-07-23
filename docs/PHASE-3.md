# Phase 3 — Restaurant ingestion pipeline

Status of the Phase 3 build (roadmap [doc 10](10-roadmap.md)). Goal: a source (URL or
API doc) becomes a **reviewed** knowledge draft + a capability map — the "magic
moment." Prices never go live without a human approving them (ADR-012).

## What's implemented

**`libs/ordy-ingest`** — the pipeline, pure over its ports (stdlib + ordy-core), so
the intelligence is unit-testable without a browser or an LLM:
- **Extraction** (`extract.py`): schema.org **JSON-LD** menu reader — `Menu` /
  `MenuSection` / `MenuItem`, multi-offer → variants, `Restaurant.openingHoursSpecification`
  → hours, per-fact provenance. An `LLMExtractor` port (provider-agnostic, ADR-008)
  fills gaps for unstructured sites; a `NullLLMExtractor` backs dev/tests.
- **Prices** (`prices.py`): locale-tolerant → integer minor units, exponent-aware
  (TND = 3 minor digits).
- **Capability analysis** (`analyze.py`): OpenAPI → REST capability candidates
  (create_order, make_reservation, check_availability, …); `build_capability_map`
  assembles the doc 04 §3 map with **native fallback** for every unmatched action.
- **Synthesis** (`synthesize.py`): merge/dedup across pages, coverage + stats, flag
  conflicts (never silently resolve).
- **Change detection** (`diff.py`): price changes / removals are substantive → routed
  to review; cosmetic changes can auto-approve.
- **Orchestration** (`orchestrator.py`): website → knowledge (+ native capabilities);
  api_doc → REST capabilities. `runner.py` is the DB-bound stage (drafts only) shared
  by the worker and the API's inline-dev path.

**`services/workers`** — Celery app (queues: ingestion / embeddings / webhooks), the
ingestion task (`ordy.ingestion.run`) over the shared runner, a beat sweep for
scheduled re-syncs, HTTP/Playwright fetcher selection, and a local/S3 storage builder.

**`services/api`** — knowledge module: register sources, trigger runs (inline in dev,
or enqueued to the worker by task name — no cross-service import), serve the review
payload (draft + provenance + capability map + warnings), and **publish approved
drafts into the menu tables**. Capability-map approval activates the map (compilation
to `restaurant_tools` lands in Phase 6).

**Data**: migration `0002_ingestion` adds `knowledge_sources`, `ingestion_runs`,
`knowledge_documents`, `capability_maps` — each under the same FORCE'd per-tenant RLS.

**Frontend**: a combined onboarding + review page — enter a URL, watch it extract,
tick items to keep, approve & publish; the capability map renders as `action → adapter`
chips.

## The invariant, preserved

Extraction produces **drafts** (`knowledge_documents.status = draft`,
`capability_maps.status = draft`). Nothing touches the live menu until
`POST /runs/{id}/review` — a human, `manager`+ role — approves. Prices are written only
in that publish step. Re-crawls diff content and route price/availability changes back
to review.

## Run it

```bash
docker compose up --build       # now includes worker + beat
cd services/api && uv run alembic upgrade head   # applies 0001 + 0002
# In the dashboard → Onboard: paste a menu URL (or an OpenAPI URL) → review → publish.
# Local without a broker: set INGEST_INLINE=true and the API runs the pipeline in-process.
```

## Validation done in this environment

The **entire pure pipeline was executed here** (Python 3.13, stdlib only) and all 6
tests pass: JSON-LD extraction (pepperoni → `[24000, 32000]` millimes, margherita →
`18500`, category "Pizzas"), synthesis coverage, OpenAPI detection (create_order →
rest, native fallback for the rest), price-change → review routing, and the website
orchestrator end-to-end. All Python across the repo compiles. The DB-bound parts
(runner persistence, publish into menu tables, Celery, real crawling) are
syntax-validated but not executed here — no Postgres/Redis/Playwright in the authoring
env; the CI workflow + `docker compose` are the reference for a live run.

## Remaining / deferred

- LLM extractor implementation against the model router (heuristic + JSON-LD ship now).
- Playwright crawler wiring in the worker (port + selection are in place; `StaticFetcher` is the baseline).
- PDF/image (OCR/vision) extraction path.
- DB-introspection + GitHub static analysis (capability candidates) — native fallback holds until then.
- Embeddings/chunks (`knowledge_chunks`, pgvector) — Phase 4.
