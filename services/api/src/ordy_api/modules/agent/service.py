"""Agent config + sandbox conversation service (doc 07 §2.6).

The sandbox runs the FULL read-only agent turn (supervisor → knowledge/conversation)
against live approved knowledge, forcing text mode, and persists every turn with its
trace so the dashboard can show route + retrieval + grounding.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from ordy_core.enums import ActionStatus, Channel, ConversationStatus, TurnRole
from ordy_core.errors import NotFound
from ordy_core.models import (
    ActionExecution,
    AgentConfig,
    Conversation,
    ConversationTurn,
    Restaurant,
)
from ordy_agent.engine import run_turn
from ordy_agent.state import ConversationState, Turn
from ordy_agent.tools_runtime import ToolRuntime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.agent_runtime import build_deps, build_policy_context
from ordy_api.modules.orders.adapter import DbNativeAdapter


def _now() -> datetime:
    return datetime.now(UTC)


async def get_or_create_config(session: AsyncSession, restaurant_id: uuid.UUID) -> AgentConfig:
    cfg = await session.scalar(
        select(AgentConfig)
        .where(AgentConfig.restaurant_id == restaurant_id, AgentConfig.is_active.is_(True))
        .limit(1)
    )
    if cfg is None:
        restaurant = await session.get(Restaurant, restaurant_id)
        cfg = AgentConfig(
            restaurant_id=restaurant_id,
            languages=list(restaurant.languages) if restaurant else ["fr"],
            persona={"restaurant_name": restaurant.name if restaurant else "our restaurant"},
        )
        session.add(cfg)
        await session.flush()
    return cfg


async def update_config(session: AsyncSession, restaurant_id: uuid.UUID, changes: dict) -> AgentConfig:
    cfg = await get_or_create_config(session, restaurant_id)
    for field, value in changes.items():
        setattr(cfg, field, value)
    await session.flush()
    return cfg


async def _persona(session: AsyncSession, restaurant_id: uuid.UUID) -> tuple[dict, str]:
    cfg = await get_or_create_config(session, restaurant_id)
    persona = dict(cfg.persona)
    persona.setdefault("restaurant_name", "our restaurant")
    language = cfg.languages[0] if cfg.languages else "fr"
    return persona, language


async def create_conversation(session: AsyncSession, restaurant_id: uuid.UUID) -> Conversation:
    cfg = await get_or_create_config(session, restaurant_id)
    conv = Conversation(
        restaurant_id=restaurant_id,
        agent_config_id=cfg.id,
        channel=Channel.SANDBOX,
        pipeline_mode="text",
        language=cfg.languages[0] if cfg.languages else "fr",
        status=ConversationStatus.ACTIVE,
        started_at=_now(),
    )
    session.add(conv)
    await session.flush()
    return conv


async def _load_conversation(session: AsyncSession, restaurant_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.restaurant_id != restaurant_id:
        raise NotFound("conversation not found")
    return conv


async def post_turn(
    session: AsyncSession, restaurant_id: uuid.UUID, conversation_id: uuid.UUID, text: str
) -> tuple[str, dict, ConversationStatus]:
    conv = await _load_conversation(session, restaurant_id, conversation_id)
    persona, language = await _persona(session, restaurant_id)

    # Rebuild agent state from stored turns.
    rows = await session.scalars(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.seq)
    )
    state = ConversationState(
        conversation_id=conversation_id, restaurant_id=restaurant_id, channel="sandbox", language=conv.language or language
    )
    for row in rows:
        state.turns.append(Turn(role=row.role.value, content=row.content or "", seq=row.seq))

    # A pending confirmation carries across turns (doc 03 §4.2) — rehydrate it from the
    # last agent turn's trace so a "yes" resolves the action it was actually about.
    last_agent_turn = await session.scalar(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id, ConversationTurn.role == TurnRole.AGENT)
        .order_by(ConversationTurn.seq.desc())
        .limit(1)
    )
    if last_agent_turn is not None and last_agent_turn.content_json:
        state.pending_confirmation = last_agent_turn.content_json.get("pending_confirmation")

    seq = len(state.turns)
    state.add_turn("customer", text)
    session.add(
        ConversationTurn(
            restaurant_id=restaurant_id, conversation_id=conversation_id, seq=seq,
            role=TurnRole.CUSTOMER, content=text,
        )
    )

    context = await build_policy_context(session, restaurant_id, channel="sandbox")
    # Phase 7: confirmed actions now write REAL orders/reservations via the DB adapter.
    runtime = ToolRuntime(
        context=context,
        executor=DbNativeAdapter(
            session,
            restaurant_id,
            menu=context.menu,
            currency=context.currency,
            channel=Channel.SANDBOX,
            conversation_id=conversation_id,
            delivery_fee_minor=context.delivery.fee_minor,
        ),
    )
    deps = build_deps(session, restaurant_id, persona, tools=runtime)
    started = time.monotonic()
    result = await run_turn(state, deps)
    latency_ms = int((time.monotonic() - started) * 1000)

    _persist_actions(session, restaurant_id, conversation_id, runtime, result.trace)
    if state.pending_confirmation:
        result.trace["pending_confirmation"] = state.pending_confirmation

    session.add(
        ConversationTurn(
            restaurant_id=restaurant_id, conversation_id=conversation_id, seq=seq + 1,
            role=TurnRole.AGENT, content=result.reply, content_json=result.trace, latency_ms=latency_ms,
        )
    )
    if state.status == "escalated":
        conv.status = ConversationStatus.ESCALATED
    return result.reply, result.trace, conv.status


_STAGE_STATUS = {
    "rejected": ActionStatus.REJECTED,
    "awaiting_confirmation": ActionStatus.AWAITING_CONFIRMATION,
    "declined": ActionStatus.DECLINED,
    "expired": ActionStatus.EXPIRED,
}


def _persist_actions(
    session: AsyncSession,
    restaurant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    runtime: ToolRuntime,
    trace: dict,
) -> None:
    """Append-only action audit (doc 03 §4.2). Written by the gate's own record of the
    turn, not by cooperative logging."""
    if trace.get("route") != "action":
        return
    stage = trace.get("stage")
    if stage == "executed":
        status = ActionStatus.SUCCEEDED if trace.get("outcome") == "succeeded" else ActionStatus.FAILED
    else:
        status = _STAGE_STATUS.get(str(stage), ActionStatus.PROPOSED)

    action_id = trace.get("action_id")
    proposal = next(
        (entry for entry in runtime.audit if entry.get("action_id") == action_id and "args" in entry), {}
    )
    session.add(
        ActionExecution(
            restaurant_id=restaurant_id,
            conversation_id=conversation_id,
            tool_key=str(trace.get("tool") or proposal.get("tool") or "unknown"),
            status=status,
            input=proposal.get("args", {}),
            validation_report=trace.get("validation", {}),
            rejection_code=(trace.get("validation") or {}).get("rejection_code"),
            confirmation=trace.get("confirmation"),
            adapter=runtime.executor.name,
            external_ref=trace.get("external_ref"),
            idempotency_key=str(action_id) if action_id else None,
        )
    )


async def list_conversations(session: AsyncSession, restaurant_id: uuid.UUID) -> list[Conversation]:
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.restaurant_id == restaurant_id)
        .order_by(Conversation.started_at.desc())
        .limit(50)
    )
    return list(rows)


async def get_conversation_with_turns(
    session: AsyncSession, restaurant_id: uuid.UUID, conversation_id: uuid.UUID
) -> tuple[Conversation, list[ConversationTurn]]:
    conv = await _load_conversation(session, restaurant_id, conversation_id)
    turns = await session.scalars(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.seq)
    )
    return conv, list(turns)
