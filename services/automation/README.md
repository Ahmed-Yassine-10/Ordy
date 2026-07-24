# services/automation — Sandbox runner (Phase 8)

Executes **verified** browser workflows for restaurants whose only interface is their
website. See [docs/04-ingestion.md §6](../../docs/04-ingestion.md) and
[docs/08-security.md §5](../../docs/08-security.md).

## Hardening (doc 08 §5)

| Layer | Control |
|---|---|
| Image | Minimal Playwright base, pinned digest, **non-root**, read-only root FS, tmpfs scratch |
| Runtime | Dedicated node pool, gVisor/Kata where available, CPU/mem/pids limits, 120s hard wall-clock |
| Network | Default-deny egress; allowlist = the approved target domain only. **No route to cluster services, RFC1918, or 169.254.169.254** |
| Input | Workflow definitions are approved artifacts, hash-pinned at dispatch; parameters schema-validated by the action gate first |
| Execution | Deterministic replay — **no LLM in the loop**; `never_fill` refuses card/CVV/password fields |
| Output | Screenshots + DOM snapshots to a per-run S3 prefix via a scoped token. **The sandbox has no database credentials** |
| Blast radius | One run = one container = one order attempt; never reused across tenants |

The egress allowlist and payment-field refusal are enforced twice: in-process by
`ordy-automation`'s guards (unit-tested) **and** at the network/container layer by the
Kubernetes NetworkPolicy + runtime class.

## Status

`driver.py` implements the `BrowserDriver` port against Playwright. The live dispatch
loop and the NetworkPolicy manifests land with the Phase 10 cluster work; the guards,
replay logic, and degrade chain are complete and tested in `libs/ordy-automation`.
