# services/automation — Sandboxed browser runner (Phase 8)

Hardened Playwright runners that execute AI-generated, human-verified workflows
deterministically (no LLM in the execution loop) against restaurant websites that
have no API. Non-root, read-only FS, egress allow-listed, every step screenshotted.
Never enters payment card data.

See [docs/04-ingestion.md §6](../../docs/04-ingestion.md) and
[docs/08-security.md §5](../../docs/08-security.md). Not yet implemented — scaffolded
in Phase 8.
