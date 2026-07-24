"""Reciprocal Rank Fusion (doc 03 §3.2): merge the vector ranking and the lexical
ranking into one, robust to score-scale differences between the two retrievers."""

from __future__ import annotations


def reciprocal_rank_fusion(
    rankings: list[list[str]], *, k: int = 60, weights: list[float] | None = None
) -> list[tuple[str, float]]:
    """Fuse ranked id lists. ``score = Σ weight / (k + rank)``; higher is better.

    ``k`` damps the contribution of low-ranked items (the standard RRF constant).
    """
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("weights must match rankings length")
    scores: dict[str, float] = {}
    for i, ranking in enumerate(rankings):
        weight = weights[i] if weights else 1.0
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
