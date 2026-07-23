# services/workers — Background jobs (Phase 3)

Celery workers (Redis broker) for the ingestion pipeline, embeddings, webhook
delivery, and scheduled re-syncs. Every task entrypoint sets tenant context
exactly like a request handler (RLS discipline extends to jobs — ADR-006).

See [docs/04-ingestion.md](../../docs/04-ingestion.md). Not yet implemented —
scaffolded in Phase 3.
