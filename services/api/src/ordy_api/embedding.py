"""Embedder factory (ADR-008). Dev uses the deterministic HashingEmbedder; prod points
at the model router's EMBEDDING tier. Dim must match the ``knowledge_chunks`` column."""

from __future__ import annotations

from functools import lru_cache

from ordy_rag.embed import Embedder, HashingEmbedder, NullEmbedder

from ordy_api.config import get_settings


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    backend = settings.embedding_backend
    if backend == "null":
        return NullEmbedder(dim=settings.embedding_dim)
    if backend == "openai":  # wired with the model router; falls back for now
        raise NotImplementedError("openai embedding backend lands with the model router")
    return HashingEmbedder(dim=settings.embedding_dim)
