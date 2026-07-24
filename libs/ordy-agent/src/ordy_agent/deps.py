"""Injected dependencies for a turn. The retriever is a callable so the engine stays
storage-agnostic: an in-memory RAG store in tests, pgvector hybrid search in the API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ordy_rag.models import RetrievedChunk

from ordy_agent.brain import AgentBrain

Retriever = Callable[[str, int], Awaitable[list[RetrievedChunk]]]


@dataclass(slots=True)
class AgentDeps:
    brain: AgentBrain
    retrieve: Retriever
    persona: dict = field(default_factory=dict)
    max_write_actions: int = 5  # reserved for the Phase 6 action budget
