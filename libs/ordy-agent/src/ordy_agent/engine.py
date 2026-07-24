"""Turn engine (doc 03 §1). Sequential driver over the role logic — the Phase 5
read-only path (supervisor → knowledge | conversation | handoff). Phase 6 promotes the
LangGraph runtime in ``graph.py`` to primary and adds Planning/Validation/Execution
with the confirmation interrupt.

Grounding is enforced here in code regardless of which brain answered."""

from __future__ import annotations

from dataclasses import dataclass, field

from ordy_rag.ground import check_grounding
from ordy_rag.rewrite import rule_rewrite

from ordy_agent.deps import AgentDeps
from ordy_agent.state import ConversationState, Intent


@dataclass(slots=True)
class TurnResult:
    state: ConversationState
    reply: str
    trace: dict = field(default_factory=dict)


async def run_turn(state: ConversationState, deps: AgentDeps) -> TurnResult:
    user = state.last_user() or ""
    intent = await deps.brain.classify_intent(user, [t.content for t in state.turns])
    state.intent = intent

    if intent == Intent.HANDOFF:
        reply = deps.persona.get("handoff") or "Let me get a colleague to help you right away."
        state.status = "escalated"
        return _finish(state, reply, {"route": "handoff", "intent": intent.value})

    if intent == Intent.SMALLTALK:
        reply = await deps.brain.smalltalk(state, deps.persona, state.language)
        return _finish(state, reply, {"route": "conversation", "intent": intent.value})

    # INQUIRE — and, in Phase 5, any action intent — is answered from knowledge only.
    query = rule_rewrite(user)
    chunks = await deps.retrieve(query, 5)
    state.retrieval_context = chunks
    reply = await deps.brain.answer_from_knowledge(user, chunks, deps.persona, state.language)

    report = check_grounding(reply, chunks)
    if report.should_regenerate:
        # Don't let an ungrounded number reach the customer; fall back to a safe line.
        reply = deps.persona.get("unsure") or (
            "I'm not fully sure about that — let me connect you with a colleague."
        )
        if not chunks:
            state.status = "escalated"

    trace = {
        "route": "knowledge",
        "intent": intent.value,
        "retrieved": [
            {"chunk_id": c.chunk_id, "score": round(c.score, 4), "source": c.provenance.get("source_url")}
            for c in chunks
        ],
        "grounding": {"grounded": report.grounded, "unsupported": report.unsupported_numbers},
    }
    return _finish(state, reply, trace)


def _finish(state: ConversationState, reply: str, trace: dict) -> TurnResult:
    state.add_turn("agent", reply)
    return TurnResult(state=state, reply=reply, trace=trace)
