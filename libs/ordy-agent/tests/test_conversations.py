"""Golden conversation evals (doc 03 §9) — deterministic, no provider, no DB."""

from __future__ import annotations

import uuid

import pytest
from ordy_agent.brain import RuleBasedBrain
from ordy_agent.deps import AgentDeps
from ordy_agent.engine import run_turn
from ordy_agent.state import ConversationState
from ordy_rag.embed import HashingEmbedder
from ordy_rag.retrieve import hybrid_retrieve
from ordy_rag.store import InMemoryVectorStore

pytestmark = pytest.mark.asyncio

KB = {
    "pep": "Pizzas\nPizza Pepperoni Medium 24000 Large 32000 spicy pepperoni mozzarella",
    "marg": "Pizzas\nMargherita 18500 tomato mozzarella basil vegetarian sans viande",
    "hours": "Hours\nOpen daily 11:00 to 23:00 pickup and delivery",
}


def _deps() -> AgentDeps:
    emb = HashingEmbedder(dim=512)
    store = InMemoryVectorStore()
    for cid, text in KB.items():
        store.add(cid, emb.embed([text])[0], text, document_id="d", provenance={"source_url": "https://r/menu"})

    async def retrieve(q: str, k: int):
        return hybrid_retrieve(store, q, emb, k=k)

    persona = {"greeting": "Ahla w sahla! Welcome to Pizza Rustica.", "restaurant_name": "Pizza Rustica"}
    return AgentDeps(brain=RuleBasedBrain(), retrieve=retrieve, persona=persona)


def _state(lang: str = "en") -> ConversationState:
    return ConversationState(conversation_id=uuid.uuid4(), restaurant_id=uuid.uuid4(), language=lang)


async def _ask(state: ConversationState, deps: AgentDeps, text: str):
    state.add_turn("customer", text)
    return await run_turn(state, deps)


async def test_greeting_routes_to_conversation() -> None:
    r = await _ask(_state(), _deps(), "hello there")
    assert r.trace["route"] == "conversation"
    assert "Ahla" in r.reply or "Welcome" in r.reply


async def test_price_question_is_grounded() -> None:
    r = await _ask(_state(), _deps(), "how much is the pepperoni pizza?")
    assert r.trace["route"] == "knowledge"
    assert r.trace["grounding"]["grounded"] is True
    assert "32000" in r.reply
    assert r.trace["retrieved"][0]["source"] == "https://r/menu"


async def test_vegetarian_question_finds_margherita() -> None:
    r = await _ask(_state(), _deps(), "do you have vegetarian options?")
    assert "argh" in r.reply.lower() or "vegetarian" in r.reply.lower()


async def test_handoff_escalates() -> None:
    state = _state()
    r = await _ask(state, _deps(), "can I talk to a human please")
    assert r.trace["route"] == "handoff"
    assert state.status == "escalated"


async def test_multi_turn_accumulates_state() -> None:
    deps, state = _deps(), _state()
    await _ask(state, deps, "hi")
    r = await _ask(state, deps, "what are your hours?")
    assert r.trace["route"] == "knowledge"
    assert "11:00" in r.reply or "23:00" in r.reply
    assert len(state.turns) == 4  # 2 customer + 2 agent
