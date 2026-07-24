"""Injected dependencies for a turn. The retriever is a callable so the engine stays
storage-agnostic: an in-memory RAG store in tests, pgvector hybrid search in the API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ordy_rag.models import RetrievedChunk

from ordy_agent.brain import AgentBrain
from ordy_agent.tools_runtime import ToolRuntime

Retriever = Callable[[str, int], Awaitable[list[RetrievedChunk]]]


@dataclass(slots=True)
class AgentDeps:
    brain: AgentBrain
    retrieve: Retriever
    persona: dict = field(default_factory=dict)
    # When None the agent is read-only (Phase 5 behavior): action intents are answered
    # from knowledge instead of proposing tool calls.
    tools: ToolRuntime | None = None
