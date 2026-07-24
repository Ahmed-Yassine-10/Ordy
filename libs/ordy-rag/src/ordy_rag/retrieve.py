"""Hybrid retrieval (doc 03 §3.2): vector + lexical candidates, fused with RRF.

Storage-agnostic: works over any ``VectorStore``. Tenant isolation is enforced by the
store (RLS in the pgvector case), not here.
"""

from __future__ import annotations

from collections.abc import Callable

from ordy_rag.embed import Embedder
from ordy_rag.fuse import reciprocal_rank_fusion
from ordy_rag.models import RetrievedChunk
from ordy_rag.rewrite import rule_rewrite
from ordy_rag.store import InMemoryVectorStore


def hybrid_retrieve(
    store: InMemoryVectorStore,
    query: str,
    embedder: Embedder,
    *,
    k: int = 5,
    rewriter: Callable[[str], str] | None = rule_rewrite,
    candidate_multiplier: int = 3,
) -> list[RetrievedChunk]:
    rewritten = rewriter(query) if rewriter else query
    query_vec = embedder.embed([rewritten])[0]
    n = max(k, k * candidate_multiplier)

    vector_ids = [cid for cid, _ in store.search_vector(query_vec, n)]
    lexical_ids = [cid for cid, _ in store.search_lexical(rewritten, n)]
    fused = reciprocal_rank_fusion([vector_ids, lexical_ids])[:k]

    results: list[RetrievedChunk] = []
    for chunk_id, score in fused:
        rec = store.get(chunk_id)
        results.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                content=rec.text,
                score=score,
                document_id=rec.meta.get("document_id"),
                provenance=rec.meta.get("provenance", {}),
                language=rec.meta.get("language"),
            )
        )
    return results
