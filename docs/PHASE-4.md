# Phase 4 — Knowledge base + RAG

Status of the Phase 4 build (roadmap [doc 10](10-roadmap.md)). Goal: approved knowledge
becomes retrievable, **citable** truth the agent can ground its answers in — searchable
iff approved.

## What's implemented

**`libs/ordy-rag`** — retrieval, pure over its ports (stdlib + ordy-core), so the whole
pipeline is unit-testable without a DB or a provider:
- **Chunking** (`chunk.py`): heading-aware, ~target-token windows with overlap; each
  chunk keeps its section heading path.
- **Embeddings** (`embed.py`): an `Embedder` port (ADR-008) with a deterministic
  `HashingEmbedder` (no network — reproducible dev/test vectors) and a `NullEmbedder`.
- **Fusion** (`fuse.py`): Reciprocal Rank Fusion — merges vector + lexical rankings
  robustly across score scales.
- **Retrieval** (`retrieve.py`): hybrid over any `VectorStore`; `InMemoryVectorStore`
  (cosine + token-overlap) backs tests/eval.
- **Query rewrite** (`rewrite.py`): normalize + small FR/EN/Derja menu-term expansions;
  LLM pronoun resolution plugs in behind the `QueryRewriter` port.
- **Grounding** (`ground.py`): heuristic that flags any price-like number the agent
  says which isn't present in the retrieved context — the highest-risk hallucination
  for a price-quoting voice agent.

**Data**: migration `0003` adds `knowledge_chunks` — `vector(1536)` embedding, an
**HNSW cosine index**, a generated `fts` tsvector + **GIN index**, under the same
FORCE'd per-tenant RLS.

**`services/api`**:
- **pgvector retrieval** (`modules/knowledge/retrieval.py`): vector candidates via the
  HNSW index + lexical via FTS, fused with RRF; tenant isolation from RLS, provenance
  attached to every hit.
- **Embed-at-publish**: `publish_review` chunks + embeds the approved menu document and
  inserts `knowledge_chunks` **in the same transaction as the approval flip** — a chunk
  is searchable iff approved (ADR-005/012). Re-publish replaces the document's chunks.
- **`POST /restaurants/{id}/knowledge/search`**: the retrieval debug endpoint (also the
  path the agent will use from Phase 5), returning content + score + provenance.
- Embedder factory (`embedding.py`): hashing in dev, model-router EMBEDDING tier in prod.

**Frontend**: a Knowledge page — ask a question, see the ranked chunks the agent would
retrieve, each with a click-through to its source ("why did it say that").

## The invariant, preserved

Embeddings are written only inside the publish transaction, keyed to an approved
document. Nothing is retrievable before a human approves it, and re-crawls that change
prices re-enter review before re-indexing.

## Validation done in this environment

The **full retrieval pipeline runs here** (Python 3.13, stdlib) — 5 tests pass:
heading-aware chunking, RRF ordering, **retrieval hit@3 = 100%** on a 4-query menu eval
set, provenance carried onto results, and grounding flagging a hallucinated number.
All repo Python compiles. The pgvector path (HNSW/FTS SQL, embed-at-publish) is
syntax-validated but not executed here — no Postgres/pgvector in the authoring env; CI
(`chunks_hnsw_idx` + `chunks_fts_idx` created by migration 0003) and `docker compose`
are the reference for a live run.

## Remaining / deferred

- OpenAI (model-router) embedder implementation — port + factory are in place;
  `HashingEmbedder` backs dev/CI.
- Reranking pass (optional, doc 03 §3.2) after fusion.
- Retrieval latency benchmark (< 100 ms p95 exit target) — needs a live pgvector corpus.
- Indexing hours/policy documents (menu document is indexed now); same path, more doc types.
- Embedding-as-a-job option for very large corpora (inline-at-publish is fine at menu scale).
