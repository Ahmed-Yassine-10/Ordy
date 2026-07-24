"""Turn engine (doc 03 §1).

Phase 5 gave read-only routing (knowledge / conversation / handoff). Phase 6 adds the
action path: plan → **deterministic gate** → confirmation interrupt → idempotent
execution. The engine never trusts the brain: rejection reasons come back as codes the
Conversation role turns into graceful repair, and nothing executes without a fresh,
explicit confirmation of a system-generated summary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ordy_rag.ground import check_grounding
from ordy_rag.rewrite import rule_rewrite
from ordy_tools.confirm import (
    ConfirmationRequest,
    ConfirmationState,
    interpret_response,
    request_confirmation,
    resolve_confirmation,
)
from ordy_tools.executor import execute_action
from ordy_tools.models import ActionStatus
from ordy_tools.policy import validate_action

from ordy_agent.deps import AgentDeps
from ordy_agent.state import ConversationState, Intent

_ACTION_INTENTS = {Intent.ORDER, Intent.RESERVE, Intent.MODIFY, Intent.CANCEL}


@dataclass(slots=True)
class TurnResult:
    state: ConversationState
    reply: str
    trace: dict = field(default_factory=dict)


async def run_turn(state: ConversationState, deps: AgentDeps) -> TurnResult:
    user = state.last_user() or ""

    # A pending confirmation owns the turn: this utterance is a yes/no, not a new intent.
    if deps.tools is not None and state.pending_confirmation:
        return await _resolve_pending(state, deps, user)

    intent = await deps.brain.classify_intent(user, [t.content for t in state.turns])
    state.intent = intent

    if intent == Intent.HANDOFF:
        reply = deps.persona.get("handoff") or "Let me get a colleague to help you right away."
        state.status = "escalated"
        return _finish(state, reply, {"route": "handoff", "intent": intent.value})

    if intent == Intent.SMALLTALK:
        reply = await deps.brain.smalltalk(state, deps.persona, state.language)
        return _finish(state, reply, {"route": "conversation", "intent": intent.value})

    if intent in _ACTION_INTENTS and deps.tools is not None:
        return await _action_turn(state, deps, user, intent)

    return await _knowledge_turn(state, deps, user, intent)


# ---------------- knowledge (read-only) ----------------


async def _knowledge_turn(state: ConversationState, deps: AgentDeps, user: str, intent: Intent) -> TurnResult:
    chunks = await deps.retrieve(rule_rewrite(user), 5)
    state.retrieval_context = chunks
    reply = await deps.brain.answer_from_knowledge(user, chunks, deps.persona, state.language)

    report = check_grounding(reply, chunks)
    if report.should_regenerate:
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


# ---------------- action gate ----------------


async def _action_turn(state: ConversationState, deps: AgentDeps, user: str, intent: Intent) -> TurnResult:
    tools = deps.tools
    assert tools is not None

    plan = await deps.brain.plan_actions(user, tools.context.menu)
    if not plan.steps:
        # Couldn't identify what to order — answer from knowledge instead of guessing.
        return await _knowledge_turn(state, deps, user, intent)

    step = plan.steps[0]
    spec = tools.catalog.get(step.tool)
    if spec is None:  # a tool outside the platform catalog can never execute
        return _finish(
            state,
            "I can't do that here.",
            {"route": "action", "intent": intent.value, "tool": step.tool, "rejected": "UNKNOWN_TOOL"},
        )

    report = validate_action(spec, step.args, tools.context)
    action_id = str(uuid.uuid4())
    tools.audit.append(
        {"action_id": action_id, "tool": spec.key, "args": step.args, "validation": report.as_dict()}
    )

    trace: dict = {
        "route": "action",
        "intent": intent.value,
        "tool": spec.key,
        "action_id": action_id,
        "validation": report.as_dict(),
    }

    if not report.passed:
        # The rejection reason is what the customer hears — repair, not a dead end.
        reply = report.human_message or "I can't do that right now."
        trace["stage"] = "rejected"
        return _finish(state, reply, trace)

    if report.requires_confirmation:
        confirmation = request_confirmation(
            action_id=action_id, tool_key=spec.key, summary=report.summary or spec.title,
            args=step.args, now=tools.now(), turn_seq=len(state.turns),
        )
        state.pending_confirmation = confirmation.as_dict()
        trace["stage"] = "awaiting_confirmation"
        trace["confirmation"] = {"summary": confirmation.summary, "expires_at": confirmation.expires_at.isoformat()}
        return _finish(state, f"{report.summary}. Shall I place it?", trace)

    outcome = await execute_action(spec, step.args, tools.executor, idempotency_key=action_id)
    return _finish(state, _outcome_reply(outcome), {**trace, "stage": "executed", "outcome": outcome.status.value})


async def _resolve_pending(state: ConversationState, deps: AgentDeps, user: str) -> TurnResult:
    tools = deps.tools
    assert tools is not None
    confirmation = ConfirmationRequest.from_dict(state.pending_confirmation or {})

    decision = interpret_response(user)
    if decision is None:
        # Ambiguous is NOT consent — re-read the summary, keep the gate closed.
        return _finish(
            state,
            f"Just to confirm: {confirmation.summary}. Should I go ahead?",
            {"route": "action", "stage": "awaiting_confirmation", "action_id": confirmation.action_id},
        )

    result = resolve_confirmation(
        confirmation, approved=decision, now=tools.now(), current_turn_seq=len(state.turns)
    )
    state.pending_confirmation = None
    trace = {
        "route": "action",
        "action_id": confirmation.action_id,
        "tool": confirmation.tool_key,
        "confirmation_state": result.value,
    }

    if result is ConfirmationState.DECLINED:
        return _finish(state, "No problem — I haven't placed anything.", {**trace, "stage": "declined"})
    if result is ConfirmationState.EXPIRED:
        return _finish(
            state,
            "That confirmation expired — would you like me to go through it again?",
            {**trace, "stage": "expired"},
        )

    spec = tools.catalog[confirmation.tool_key]
    outcome = await execute_action(
        spec, confirmation.args, tools.executor, idempotency_key=confirmation.action_id
    )
    tools.context.actions_taken += 1
    tools.audit.append(
        {"action_id": confirmation.action_id, "tool": spec.key, "outcome": outcome.status.value,
         "external_ref": outcome.external_ref}
    )
    return _finish(
        state,
        _outcome_reply(outcome),
        {**trace, "stage": "executed", "outcome": outcome.status.value, "external_ref": outcome.external_ref},
    )


def _outcome_reply(outcome) -> str:  # type: ignore[no-untyped-def]
    if outcome.status is ActionStatus.SUCCEEDED:
        ref = outcome.external_ref or ""
        eta = (outcome.output or {}).get("eta_minutes")
        base = f"Done! Your order is confirmed{f' — reference {ref}' if ref else ''}."
        return f"{base} It should be ready in about {eta} minutes." if eta else base
    return "Something went wrong placing that — let me get a colleague to help you."


def _finish(state: ConversationState, reply: str, trace: dict) -> TurnResult:
    state.add_turn("agent", reply)
    return TurnResult(state=state, reply=reply, trace=trace)
