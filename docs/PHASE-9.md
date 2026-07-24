# Phase 9 — Security hardening

Status of the Phase 9 build (roadmap [doc 10](10-roadmap.md)). Security was a CI gate from
Phase 2; this phase is the **focused pass** that turns continuous work into an auditable
posture — and it is the phase with the most work that only a live environment can finish.

## What's implemented

**`libs/ordy-security`** additions, all pure and tested:
- **`redaction.py`** — PII/secret redaction at the logging & tracing boundary. Shape-based
  (phone, email, card, API key, JWT) **and** key-based (`password`, `authorization`,
  `connection_string`, …), because a value under `password` must be masked even when it
  looks harmless. A stray `logger.info(request_body)` cannot leak.
- **`dsr.py`** — GDPR Arts. 15 & 17. Export produces a portable bundle; erasure
  **anonymizes rather than deletes**: identity destroyed, **financial and audit integrity
  preserved**, transcripts replaced with length-preserving markers, and a stable
  non-reversible pseudonym so repeat requests are detectable without keeping the identifier.
- **`limits.py`** — token-bucket rate limiting (keyed per customer/tenant/platform) and a
  **vendor-spend circuit breaker** with a rolling window and half-open probe: an agent
  platform's fuse box, so a runaway loop degrades to safe responses instead of billing
  through an incident.
- **`vault.py`** — envelope encryption for restaurant credentials: per-secret DEK wrapped
  by a KMS master key, `vault:` references in configs, and a guard that **refuses to store
  a literal secret** where a reference belongs. Production uses AES-GCM via `cryptography`;
  this module deliberately ships **no homemade cipher**.
- **`retention.py`** — retention policy evaluation where tenant overrides may only
  **shorten**, never exceed platform ceilings.

**API/workers** — owner-only DSR export & erasure endpoints (audited), and a nightly
retention job wired into beat that redacts aged transcripts and purges operational rows.

**Docs** — [SECURITY.md](../SECURITY.md) (posture, reporting, and an explicit *known gaps*
section) and the [incident response runbook](runbooks/incident-response.md) with severity
levels, kill switches, and per-scenario playbooks written to be followed at 3am.

## Validation done in this environment

**116 unit tests pass** across the repo — 19 new in Phase 9. The ones that matter:

- **Erasure preserves the books**: after Art. 17, `total_minor`, currency and status
  survive while address, note and identity are gone — a restaurant's accounts must not
  develop holes because a customer exercised their rights.
- **Redaction**: phone/email/card/API-key shapes masked in free text; secret-shaped **keys**
  masked regardless of value; nested structures walked.
- **Pseudonyms** stable per salt, different across salts, and non-reversible.
- **Rate limiting**: burst then throttle, refill over time, per-key isolation.
- **Cost breaker**: trips over budget, blocks while open, half-opens after cooldown, and
  rolls old spend out of the window.
- **Vault**: envelope round-trip with plaintext never in the stored ciphertext; configs
  rejected when they carry a literal secret instead of a `vault:` reference.
- **Retention**: cutoffs correct, and a tenant asking to keep audio for 5 years is clamped
  to the 90-day ceiling.

Writing these caught a **real bug**: `TokenBucket` used a falsy check on `updated_at`, so a
bucket created at `t=0` (a monotonic clock legitimately starts there) never refilled —
every caller would have been permanently throttled after its first burst. Fixed.

## Remaining — and honest about it

These are the Phase 9 exit criteria that **cannot** be met from this environment, and none
of them should be considered done:

- **External penetration test** (API, tenant isolation, sandbox escape, voice abuse) and
  remediation — the gating item before GA.
- **Secrets rotation drill** and **backup/restore drill** (RPO ≤ 15 min, RTO ≤ 4h) against
  real infrastructure.
- **Tabletop incident exercise** — the runbook is written but unrehearsed.
- **Vendor DPA review** closure for the LLM/STT/TTS providers.
- Rate-limit middleware is not yet mounted on the API request path (the limiter is built
  and tested; wiring lands with the production config).
