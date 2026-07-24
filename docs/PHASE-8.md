# Phase 8 — Website automation

Status of the Phase 8 build (roadmap [doc 10](10-roadmap.md)). Execution for the long
tail: restaurants whose only interface is their **website**. Workflows are AI-*generated*
at onboarding, human-*verified*, then **deterministically replayed** — no model in the
execution loop (ADR-011).

## What's implemented

**`libs/ordy-automation`** (new, pure) — the workflow engine and its guards:
- **`safety.py`** — the two hard rules, enforced by the runner rather than trusted to the
  workflow: an **egress allowlist** (refuses private ranges, loopback, link-local and cloud
  metadata endpoints even if a workflow names them — the SSRF boundary) and
  **never-fill** (the agent never types a card number, CVV, or password). Plus selector
  sanitization and artifact masking.
- **`runner.py`** — deterministic replay over a `BrowserDriver` port: selector fallbacks,
  an assertion after every step, abort-on-failure, and a submit step that **requires a
  platform-confirmed action** so the browser layer can never place an order the action
  gate didn't approve.
- **`drift.py`** — the degrade chain: one live failure → `degraded` (orders fall back to
  Ordy immediately, staff notified) → repeats → `disabled`. A live success never silently
  re-enables a disabled workflow; only a passing verification run does.
- **`compile.py`** — trace → workflow: concrete values become `{slots}`, every step gets an
  assertion, form steps always inherit the never-fill list, and the submit step is marked
  as requiring confirmation.

**`ordy-tools`** — `BrowserAdapter`, which hands a workflow id + bound parameters to the
isolated sandbox and composes with `FallbackAdapter` from Phase 7.

**`services/automation`** — the hardened sandbox: `PlaywrightDriver` implementing the port,
and an image that runs **non-root with a read-only root filesystem and no database
credentials** ([service README](../services/automation/README.md), doc 08 §5).

**Data/API/UI** — migration `0007` (`automation_workflows`, `automation_runs` under RLS);
verify / approve / disable endpoints where **approval requires a passing verification**;
and a dashboard page with status badges, a dry-run button, and a kill switch.

## Validation done in this environment

**97 unit tests pass** across the repo — 17 new, driving the runner with a fake browser so
the sandbox's security properties are provable without Playwright:

| Exit-criteria property | Test |
|---|---|
| Metadata endpoint blocked | `169.254.169.254`, `metadata.google.internal` refused |
| RFC1918 / loopback / IPv6 loopback blocked | `10.x`, `192.168.x`, `172.16.x`, `127.0.0.1`, `[::1]` |
| Non-allowlisted domains + bad schemes blocked | `evil.example`, `file://`, `data:`, and the lookalike `evil-<domain>.attacker.com` |
| Navigation to a blocked host aborts the run | `EGRESS_BLOCKED` |
| **Card fields never typed** | a workflow asking for `card_number` is refused whole — the fake browser records **zero** fills |
| Selector injection neutralized | a crafted product name adds **no** quotes/brackets to the selector |
| Submit needs a confirmed action | run aborts `CONFIRMATION_MISSING`, submit never clicked |
| Dry run never submits | verification stops before the final click |
| Broken selector / failed assertion | run aborts with artifacts, `SELECTOR_FAILED` / `ASSERTION_FAILED` |
| Degrade chain | failure → degraded → fallback; 3 failures → disabled; success can't re-enable |

Writing these caught a **real ordering bug**: the confirmation check ran before the
dry-run check, so verification runs failed instead of stopping cleanly at the submit step.
Fixed in `runner.py`.

**Not executed here**: the Playwright driver, the live dispatch loop, and the container
hardening (non-root, read-only FS, NetworkPolicy) — no browser or cluster in the authoring
environment. The in-process guards are unit-tested; the network/container layer enforces
the same rules independently and is verified in Phase 9/10.

## Remaining / deferred

- **Live sandbox dispatch** (Celery queue → container per run) and the Kubernetes
  NetworkPolicy + runtime-class manifests (Phase 10).
- **Workflow generation from a real exploration trace** — the compiler is done and tested;
  the LLM+Playwright explorer that produces traces runs where a browser exists.
- **3 real sites ordering end-to-end** and the weekly scheduled verification sweep — both
  need live sites (Phase 8 exit criteria that can only be met with the toolchain).
- Screenshot storage wiring to the per-run S3 prefix (paths are computed; upload lands with
  the dispatch loop).
