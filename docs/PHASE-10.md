# Phase 10 — Production deployment

Status of the Phase 10 build (roadmap [doc 10](10-roadmap.md)). The goal is *boring*
production: reproducible infrastructure, safe deploys, and alerts that fire on the numbers
we promised.

**This phase is infrastructure-as-code.** It is written and syntax-validated, but nothing
here has been applied to a real cloud account from this environment. Treat it as the
reviewed target state, not as running infrastructure.

## What's written

**`infra/k8s/`** — Kustomize base + prod overlay:
- **api** — HPA on CPU (2→20), PodDisruptionBudget, read-only root FS, non-root, dropped
  capabilities, readiness/liveness probes.
- **voice** — scales on **active sessions**, not CPU, with a 10-minute termination grace
  and a drain hook: killing a pod mid-call drops a customer.
- **workers** — scales on Celery queue depth; **beat pinned to exactly one replica**.
- **automation** — the hardened sandbox: dedicated node pool, gVisor runtime class, no
  service-account token, **no database credentials**, memory-backed scratch, and a
  **default-deny NetworkPolicy** whose egress `except` list blocks link-local/metadata
  (169.254/16), all RFC1918 ranges, and loopback. This is the independent second layer
  behind `ordy-automation`'s in-process guards.
- **alerts** — SLO PrometheusRules: voice p95 latency, API 5xx burn, **action failure rate**
  (orders not reaching restaurants is the business-critical signal), vendor-spend anomaly,
  degraded workflows, and review backlog.

**`infra/terraform/`** — EU-region VPC with **per-AZ NAT** (an AZ outage must not take
voice down), RDS Postgres 16 multi-AZ with 14-day PITR and deletion protection,
ElastiCache Redis with encryption in transit and at rest, a versioned/private S3 bucket
with lifecycle rules, and a **customer-managed KMS key** with rotation that wraps the
per-secret data keys from Phase 9.

**`.github/workflows/deploy.yml`** — build once → **trivy scan (fails on HIGH/CRITICAL, so
a vulnerable image never reaches a cluster)** → forward-only migrations → kustomize apply
with pinned digests → rollout wait → smoke test → **automatic rollback on failure**.
Expand-migrate-contract means a rollback never needs a down-migration.

## SLOs

| Objective | Target |
|---|---|
| Voice-to-voice latency | p50 ≤ 800 ms · p95 ≤ 1500 ms |
| API latency (CRUD) | p95 ≤ 150 ms |
| Platform availability | 99.5% |
| Action success rate | ≥ 95% (failures fall back to native, never dropped) |

## GA checklist

Nothing below is complete; this is the list that gates launch.

- [ ] `terraform apply` for staging, then prod; restore drill executed
- [ ] External penetration test passed and criticals/highs remediated ([Phase 9](PHASE-9.md))
- [ ] Derja STT/TTS vendor selected from the benchmark spike ([doc 05 §6](05-voice.md))
- [ ] Live voice loop wired and latency SLO met for 2 consecutive weeks
- [ ] 50-concurrent-session load test passed
- [ ] 3 real sites ordering end-to-end via automation ([Phase 8](PHASE-8.md))
- [ ] On-call rotation live; tabletop exercise completed
- [ ] Status page, support flows, billing plans finalized from real metering data
- [ ] Pilot cohort (5–10 restaurants) running with weekly review

## Honest status of the whole build

Phases 1–9 produced a coherent, **116-test** codebase where the security-critical logic —
the action gate, tenant isolation design, pricing, confirmation, sandbox guards, DSR
erasure — is implemented and provable. What remains is the work that needs real
infrastructure and real vendors: the voice audio loop, live browser runs, the pentest, and
this phase's `apply`. That is the honest boundary between what has been *built* and what
has been *proven in production*.
