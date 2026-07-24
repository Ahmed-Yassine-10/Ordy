"""Retrieval data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    document_id: str | None = None
    provenance: dict = field(default_factory=dict)  # {source_url, doc_type, headings}
    language: str | None = None
