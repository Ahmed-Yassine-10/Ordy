# libs/ordy-rag — Retrieval (Phase 4)

Chunking, embedding, and hybrid retrieval (pgvector similarity + Postgres FTS,
RRF fusion) over approved knowledge chunks — all behind a `VectorStore` port so
pgvector can be swapped for a dedicated vector DB later (ADR-005).

See [docs/03-agent-engine.md §3.2](../../docs/03-agent-engine.md). Not yet implemented.
