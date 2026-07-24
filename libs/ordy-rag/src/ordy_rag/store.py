"""Vector store port (ADR-005) + an in-memory implementation for tests/eval.

Production retrieval uses a pgvector-backed store (SQL cosine + FTS) in the API; both
satisfy the same ``search_vector`` / ``search_lexical`` contract so the retrieval
orchestration in ``retrieve.py`` is storage-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ordy_rag.embed import tokenize


class VectorStore(Protocol):
    def search_vector(self, query_vec: list[float], k: int) -> list[tuple[str, float]]: ...
    def search_lexical(self, query: str, k: int) -> list[tuple[str, float]]: ...


@dataclass(slots=True)
class _Record:
    chunk_id: str
    vector: list[float]
    text: str
    tokens: set[str]
    meta: dict = field(default_factory=dict)


class InMemoryVectorStore:
    """Cosine (dot on normalized vectors) + token-overlap lexical ranking."""

    def __init__(self) -> None:
        self._records: dict[str, _Record] = {}

    def add(self, chunk_id: str, vector: list[float], text: str, **meta: object) -> None:
        self._records[chunk_id] = _Record(
            chunk_id=chunk_id, vector=vector, text=text, tokens=set(tokenize(text)), meta=dict(meta)
        )

    def get(self, chunk_id: str) -> _Record:
        return self._records[chunk_id]

    def search_vector(self, query_vec: list[float], k: int) -> list[tuple[str, float]]:
        scored = [
            (rec.chunk_id, sum(a * b for a, b in zip(query_vec, rec.vector, strict=False)))
            for rec in self._records.values()
        ]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]

    def search_lexical(self, query: str, k: int) -> list[tuple[str, float]]:
        q_tokens = tokenize(query)
        scored: list[tuple[str, float]] = []
        for rec in self._records.values():
            overlap = sum(1 for t in q_tokens if t in rec.tokens)
            if overlap:
                scored.append((rec.chunk_id, overlap / (len(rec.tokens) ** 0.5 or 1.0)))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]
