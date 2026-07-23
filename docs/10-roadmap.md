# 10 — Development Roadmap

Ten phases from architecture to production. Durations assume a small senior team (2–4 engineers) and are ranges, not promises; phases 3–5 partially parallelize once Phase 2's foundation exists. Total to GA: roughly **20–26 weeks**.

**The commercial wedge, stated plainly:** Ordy is *sellable at the end of Phase 7* — a restaurant with nothing but a menu gets a voice agent that answers questions and takes orders/reservations into the Ordy dashboard (`NativeAdapter`), with notifications and printing. Phases 8+ widen the integration surface (browser automation, POS); they are expansion, not prerequisites for revenue. Sequence sales pilots accordingly.

| Phase | Name | Duration | Depends on |
|---|---|---|---|
| 1 | Architecture & repository structure | done | — |
| 2 | Auth + SaaS dashboard foundation | 3–4 w | 1 |
| 3 | Ingestion pipeline | 3–4 w | 2 |
| 4 | Knowledge base + RAG | 2–3 w | 3 (overlaps) |
| 5 | Voice conversational agent | 3–4 w | 4 |
| 6 | Tool-calling framework | 2–3 w | 4 (overlaps 5) |
| 7 | Order execution (native + provider) | 2–3 w | 6 |
| 8 | Website automation | 3–4 w | 7 |
| 9 | Security hardening | 2–3 w | continuous, focused pass |
| 10 | Production deployment & GA | 2 w | 9 |

---

## Phase 1 — Architecture ✅

**Delivered:** this documentation set (docs 01–10): system architecture, 15 ADRs, agent/tool/safety design, ingestion + capability map spec, voice architecture with Derja strategy, full DB schema, API contract, security model, repo structure, this roadmap.

## Phase 2 — Auth + SaaS dashboard foundation

**Goal:** a deployable skeleton with real auth, tenancy, and the dashboard shell — everything later phases plug into.
**Scope:** monorepo scaffold per doc 09; `docker compose` stack; CI pipelines 1–3; Postgres schema migrations for identity/tenancy/menu core; RLS live from the first migration; JWT + refresh rotation + Google OAuth; RBAC; API keys; restaurant CRUD + members + settings; dashboard shell (auth flows, tenant switcher, settings, manual menu manager); SDK codegen loop; OTel + structured logging baseline; Stripe subscription skeleton (trial plan).
**Exit criteria:** two seeded tenants demonstrably isolated (RLS suite green in CI); a user signs up → creates a restaurant → hand-enters a menu → invites a teammate with a role — all in the deployed staging environment.

## Phase 3 — Ingestion pipeline

**Goal:** URL-in → reviewed knowledge + capability draft out (doc 04).
**Scope:** Celery infrastructure; discover/fetch/parse stages (Playwright crawling, snapshots to MinIO/S3); extraction with structured outputs (menu/hours/policies, PDF + OCR path); synthesis into draft entities; the **review UI** (side-by-side provenance, bulk approve, edits); publish path into menu tables; ingestion run live progress; scheduled re-crawl + diff + re-review queue; OpenAPI-doc analysis (capability candidates); DB introspection (read-only sync proposals). GitHub repo analysis: candidate detection only (deep static analysis deferred post-v1 if needed).
**Exit criteria:** 10 real Tunisian/French restaurant sites ingested on staging; ≥ 90% of menu items correctly extracted or correctly flagged for review (measured against hand-labeled truth); zero unapproved price ever published (enforced by test); re-crawl detects a seeded price change and routes it to review.

## Phase 4 — Knowledge base + RAG

**Goal:** approved knowledge becomes retrievable truth the agent can cite.
**Scope:** chunking + embedding pipeline (approval-transactional per ADR-005/012); hybrid retrieval (pgvector + FTS + RRF) with tenant scoping; query rewriting; retrieval debug endpoint + dashboard panel; i18n-aware retrieval (FR/EN/ar-TN queries against canonical-language menus); grounding-check plumbing; retrieval eval set (questions → expected chunks) in CI.
**Exit criteria:** retrieval p95 < 100 ms on staging corpus; retrieval eval ≥ 95% hit@3 on the curated set; "why did it say that" provenance click-through works end to end.

## Phase 5 — Voice conversational agent

**Goal:** talk to the agent about the menu, in three languages, at production latency (doc 05). Read-only — no actions yet.
**Opening spike (1 w, gates the rest):** Derja STT/TTS benchmark on a recorded ordering corpus; LiveKit self-host vs cloud decision; Mode A realtime function-call latency measurement. Outcomes recorded as ADR-016/017.
**Scope:** LiveKit rooms + widget (mic UI, live transcript, cart panel); voice workers with Mode A (EN/FR) and Mode B (Derja) pipelines; endpointing/barge-in/back-channel handling; menu-derived STT boost + TTS lexicon compilation on publish; persona/greeting config in dashboard; text sandbox (full graph, visible traces); conversation persistence + playback; latency instrumentation dashboard; golden conversation evals (knowledge-only) per language.
**Exit criteria:** voice-to-voice p50 ≤ 800 ms (EN/FR) on staging; Derja session passes native-speaker usability review against the fallback-ladder bar (doc 05 §6); barge-in truncates state correctly (eval-verified); 20-minute continuous session stable.

## Phase 6 — Tool-calling framework

**Goal:** the full action gate, live (docs 03 §3–4, 08 §6) — before any real execution exists.
**Scope:** ToolSpec catalog + `restaurant_tools` enablement UI with caps; Planning Agent with structured plans; the deterministic validation pipeline (whitelist → schema → referential/pricing → business rules → caps → confirmation) with stored validation reports; LangGraph interrupt-based confirmation flow (voice "yes" + widget tap); `action_executions` audit; executor skeleton with `NativeAdapter` stubbed to draft orders; red-team eval suite wired into CI (injection via menu content + via speech).
**Exit criteria:** every red-team case blocked by a deterministic layer (not model refusal); confirmation flow works by voice and tap with expiry; cart totals provably server-priced (evals assert model-stated totals are discarded); action audit renders in the dashboard conversation view.

## Phase 7 — Order execution 🎯 *sellable milestone*

**Goal:** confirmed plans become real orders and reservations.
**Scope:** `NativeAdapter` complete (orders + reservations state machines, order events); live operations dashboard (feed, sound, status transitions, day view calendar); customer SMS confirmations + tracking page; webhook delivery system + event catalog; **Action Provider spec + conformance runner + `RestAdapter`**; idempotency + compensation + fallback-to-native chain; usage metering on all vendor calls; billing integration with plan limits.
**Exit criteria:** end-to-end demo: crawl a real restaurant → approve → voice-order in Derja → order rings the dashboard → staff completes it — on staging, repeatedly, under a 50-concurrent-session load test; a reference Action Provider implementation passes conformance and executes orders; pilot-ready checklist signed off.

## Phase 8 — Website automation

**Goal:** execution for restaurants whose only interface is their website (docs 04 §6, 08 §5).
**Scope:** sandbox runner (hardened image, egress allowlist, artifact capture with masking); workflow generation (trace → compile with parameter slots + assertions); dashboard verification flow (watch dry-run replay, approve); `BrowserAdapter` dispatch through the action pipeline; weekly verification schedule; drift → auto-disable → fallback → notify loop; `never_fill` payment-field enforcement with tests.
**Exit criteria:** 3 real-world sites ordering end-to-end in the sandbox against staging clones or partner sites; a deliberately broken selector triggers the full degrade chain (disable → native fallback → notifications) with zero lost orders; sandbox escape test cases (SSRF, metadata endpoint, RFC1918) all blocked.

## Phase 9 — Security hardening

**Goal:** the focused pass that turns continuous security work into an auditable posture (doc 08).
**Scope:** external penetration test (API, isolation, sandbox, voice abuse) + remediation; secrets rotation drill; DSR (export/erasure) flows shipped; retention jobs live; abuse/cost circuit breakers tuned with real staging data; incident response runbook + on-call; backup/restore drill executed; DPA review of all AI vendors closed.
**Exit criteria:** pentest criticals/highs remediated and retested; RLS + red-team + sandbox suites green in CI as permanent gates; a tabletop incident exercise completed; GDPR DSR round-trip demonstrated on a real customer record.

## Phase 10 — Production deployment & GA

**Goal:** boring, observable production.
**Scope:** Terraform prod environment (managed PG with PITR, Redis HA, KMS, EU region); Kubernetes overlays (HPA policies per service, PodDisruptionBudgets, automation node pool with runtime class); CDN for web + widget; blue-green or canary deploy for `api`/`voice`; alerting (SLOs: availability, voice latency, action failure rate, vendor spend); status page; pilot cohort (5–10 restaurants) with weekly review cadence; pricing plans finalized from Phase 7 metering data.
**Exit criteria:** SLOs met for 2 consecutive weeks with pilot traffic; on-call rotation live; a full region-restore drill passed; GA checklist (legal, billing, support flows, docs site) complete.

---

## Cross-cutting workstreams (never "a phase", always running)

- **Evals**: every phase that touches prompts/models adds cases; nightly full runs; regression gates.
- **Observability**: each phase instruments what it builds; latency/cost dashboards grow with the system.
- **Security**: CI gates from Phase 2; threat model reviewed at each phase boundary; Phase 9 is the *audit*, not the beginning.
- **Docs**: ADRs appended when decisions are made (016+: Derja vendor, LiveKit hosting, POS vendor order…); API docs published from the OpenAPI artifact.

## De-risking spikes (scheduled, time-boxed)

| Spike | When | Question it answers |
|---|---|---|
| S1 Derja STT/TTS benchmark | Phase 5 start | Which vendors clear the product bar? Which fallback rung do we launch on? |
| S2 LiveKit self-host vs cloud | Phase 5 start | Ops cost vs control for our session volumes |
| S3 Realtime-API function-call latency | Phase 5 | Is Mode A's action loop fast enough, or does Mode B carry more traffic than planned? |
| S4 Extraction accuracy on 10 real sites | Phase 3 | Is the 90% bar realistic; where does review burden actually land? |
| S5 POS sandbox accounts (Square first) | Phase 7/8 boundary | Which POS adapter ships first post-v1? |

## Explicitly deferred (post-v1 backlog)

POS adapters beyond the first (Toast, Lightspeed), delivery-platform integrations (Glovo…), in-conversation card payment (tokenized), multi-location organizations, outbound campaigns (reservation reminders upsell), analytics suite beyond operational metrics, fine-tuned Derja models, marketplace of agent personas.
