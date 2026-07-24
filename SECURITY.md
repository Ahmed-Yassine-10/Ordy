# Security

Ordy is an AI agent with the ability to take real actions on a restaurant's behalf. Our
security posture starts from one assumption: **the model will, at some point, be fooled.**
Every layer below it is built so that this is survivable.

Full design: [docs/08-security.md](docs/08-security.md).

## Reporting a vulnerability

Email **security@ordy.ai** with steps to reproduce. We acknowledge within 2 business days
and aim to remediate criticals within 7 days. Please do not open public issues for
security reports, and do not test against live restaurant tenants.

## The core invariant

The LLM never touches a database, an API, or a browser directly. It can only *propose* a
typed tool call. Between that proposal and any side effect sits deterministic code:

```
whitelist → schema → referential integrity + server-side pricing → business rules
          → caps → explicit customer confirmation → idempotent execution → audit
```

The model cannot raise caps, enable tools, alter prices, or skip confirmation — those live
in tables it cannot address and code branches it cannot reach. Our red-team suite asserts
that attacks are blocked by *code*, not by the model's refusal.

## Controls at a glance

| Area | Control |
|---|---|
| **Tenant isolation** | PostgreSQL RLS with `FORCE` on every tenant table; the app role cannot bypass it. CI runs cross-tenant access tests. |
| **Prompt injection** | Retrieved content enters prompts as delimited, untrusted data; tools are accepted only from the model's function-call channel, only from the tenant's enabled manifest. |
| **Pricing** | Totals are always computed server-side from the menu. A model-supplied total is discarded. |
| **Actions** | Per-tool whitelist per tenant, value/quantity/rate caps (tenant may only *tighten*), confirmation with wall-clock **and** conversational-distance expiry. |
| **Payments** | Out of PCI scope by design: no card data enters any Ordy system, in any channel. The browser runner refuses to type card/CVV/password fields. |
| **Browser sandbox** | Non-root, read-only FS, no DB credentials, default-deny egress with a per-workflow allowlist; RFC1918, loopback, and cloud metadata endpoints refused. |
| **Secrets** | Restaurant credentials envelope-encrypted (per-secret DEK wrapped by KMS); configs hold `vault:` references only. |
| **PII** | Redaction at the log/trace boundary; phone-based customer identity with no passwords; consent-gated memory. |
| **Privacy rights** | Export (Art. 15) and erasure (Art. 17) endpoints. Erasure **anonymizes**: identity destroyed, financial and audit integrity preserved. |
| **Retention** | Nightly job; audio 30d, transcripts 12m, audit 24m by default. Tenants may shorten, never exceed platform ceilings. |
| **Abuse & cost** | Layered token buckets (customer/tenant/platform) and a vendor-spend circuit breaker that degrades to safe responses rather than billing through an incident. |
| **Audit** | Append-only `action_executions` + `audit_logs`, written by the pipeline itself rather than by cooperative logging. |

## Supply chain & CI gates

Dependency audit, SAST (ruff security rules, semgrep), secret scanning (gitleaks),
container scanning (trivy), the RLS isolation suite, and the AI red-team evals all run in
CI. A red build blocks merge.

## Known gaps (tracked, not hidden)

- External penetration test not yet performed — **required before GA** (Phase 9 exit criterion).
- Sandbox container hardening (non-root enforcement, NetworkPolicy, runtime class) is
  written but not yet exercised against a live cluster.
- Vendor DPA review is in progress; EU-region hosting is the launch target.
