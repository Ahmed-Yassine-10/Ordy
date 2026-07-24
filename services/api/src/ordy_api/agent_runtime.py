"""Assemble AgentDeps for a turn: the brain (rule-based dev / LLM prod) + a retriever
bound to the request's RLS-scoped session (pgvector hybrid search)."""

from __future__ import annotations

import uuid

from ordy_agent.brain import RuleBasedBrain
from ordy_agent.deps import AgentDeps, Retriever
from ordy_rag.models import RetrievedChunk
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.config import get_settings
from ordy_api.embedding import get_embedder
from ordy_api.modules.knowledge.retrieval import hybrid_search


def build_brain():  # type: ignore[no-untyped-def]
    backend = get_settings().agent_brain
    if backend == "llm":
        raise NotImplementedError("LLM brain lands with the model-router completion client")
    return RuleBasedBrain()


def make_retriever(session: AsyncSession, restaurant_id: uuid.UUID) -> Retriever:
    embedder = get_embedder()

    async def retrieve(query: str, k: int) -> list[RetrievedChunk]:
        hits = await hybrid_search(session, restaurant_id, query, embedder, k=k)
        return [
            RetrievedChunk(
                chunk_id=h["chunk_id"],
                content=h["content"],
                score=h["score"],
                document_id=h["document_id"],
                provenance=h["provenance"],
                language=h["language"],
            )
            for h in hits
        ]

    return retrieve


def build_deps(session: AsyncSession, restaurant_id: uuid.UUID, persona: dict) -> AgentDeps:
    return AgentDeps(
        brain=build_brain(), retrieve=make_retriever(session, restaurant_id), persona=persona
    )
