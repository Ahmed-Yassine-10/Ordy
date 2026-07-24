"""pgvector-backed hybrid retrieval (doc 03 §3.2).

Vector candidates via the HNSW cosine index, lexical candidates via the FTS GIN
index, fused with RRF. Tenant isolation is enforced by RLS on the session (the tenant
GUC is already set by ``require_tenant``), so no explicit ``restaurant_id`` filter is
needed here — though the chunk load double-checks it (defense in depth).
"""

from __future__ import annotations

import uuid

from ordy_core.models import KnowledgeChunk
from ordy_rag.embed import Embedder
from ordy_rag.fuse import reciprocal_rank_fusion
from ordy_rag.rewrite import rule_rewrite
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


async def hybrid_search(
    session: AsyncSession,
    restaurant_id: uuid.UUID,
    query: str,
    embedder: Embedder,
    *,
    k: int = 5,
    candidate_multiplier: int = 3,
) -> list[dict]:
    rewritten = rule_rewrite(query)
    query_vec = embedder.embed([rewritten])[0]
    n = max(k, k * candidate_multiplier)

    # Vector candidates (HNSW cosine). Null-embedding rows sort last.
    vector_rows = await session.execute(
        select(KnowledgeChunk.id)
        .order_by(KnowledgeChunk.embedding.cosine_distance(query_vec))
        .limit(n)
    )
    vector_ids = [str(r[0]) for r in vector_rows]

    # Lexical candidates (FTS). RLS still applies to this raw query.
    lexical_rows = await session.execute(
        text(
            "SELECT id::text FROM knowledge_chunks "
            "WHERE fts @@ plainto_tsquery('simple', :q) "
            "ORDER BY ts_rank(fts, plainto_tsquery('simple', :q)) DESC LIMIT :n"
        ),
        {"q": rewritten, "n": n},
    )
    lexical_ids = [r[0] for r in lexical_rows]

    fused = reciprocal_rank_fusion([vector_ids, lexical_ids])[:k]
    if not fused:
        return []

    ids = [uuid.UUID(cid) for cid, _ in fused]
    rows = await session.scalars(
        select(KnowledgeChunk).where(
            KnowledgeChunk.id.in_(ids), KnowledgeChunk.restaurant_id == restaurant_id
        )
    )
    by_id = {str(c.id): c for c in rows}

    results: list[dict] = []
    for cid, score in fused:
        chunk = by_id.get(cid)
        if chunk is None:
            continue
        results.append(
            {
                "chunk_id": cid,
                "content": chunk.content,
                "score": round(score, 6),
                "document_id": str(chunk.document_id),
                "provenance": chunk.meta.get("provenance", {}),
                "language": chunk.language,
            }
        )
    return results
