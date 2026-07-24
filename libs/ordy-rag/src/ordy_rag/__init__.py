"""ordy-rag — retrieval over approved restaurant knowledge (doc 03 §3.2).

Pure, dependency-free stages (chunking, RRF fusion, hybrid retrieval over a store
port) are unit-testable without a database or a real embedding provider. The
production embedder + pgvector store plug in behind ports (ADR-005/008).
"""

from ordy_rag.chunk import ChunkDraft, chunk_markdown
from ordy_rag.embed import Embedder, HashingEmbedder, NullEmbedder
from ordy_rag.fuse import reciprocal_rank_fusion
from ordy_rag.ground import GroundingReport, check_grounding
from ordy_rag.models import RetrievedChunk
from ordy_rag.retrieve import hybrid_retrieve
from ordy_rag.rewrite import rule_rewrite
from ordy_rag.store import InMemoryVectorStore, VectorStore

__all__ = [
    "ChunkDraft",
    "Embedder",
    "GroundingReport",
    "HashingEmbedder",
    "InMemoryVectorStore",
    "NullEmbedder",
    "RetrievedChunk",
    "VectorStore",
    "check_grounding",
    "chunk_markdown",
    "hybrid_retrieve",
    "reciprocal_rank_fusion",
    "rule_rewrite",
]
