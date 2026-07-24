"""Agent config + sandbox conversation service (doc 07 §2.6).

The sandbox runs the FULL read-only agent turn (supervisor → knowledge/conversation)
against live approved knowledge, forcing text mode, and persists every turn with its
trace so the dashboard can show route + retrieval + grounding.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from ordy_core.enums import Channel, ConversationStatus, TurnRole
from ordy_core.errors import NotFound
from ordy_core.models import AgentConfig, Conversation, ConversationTurn, Restaurant
from ordy_agent.engine import run_turn
from ordy_agent.state import ConversationState, Turn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.agent_runtime import build_deps


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

    seq = len(state.turns)
    state.add_turn("customer", text)
    session.add(
        ConversationTurn(
            restaurant_id=restaurant_id, conversation_id=conversation_id, seq=seq,
            role=TurnRole.CUSTOMER, content=text,
        )
    )

    deps = build_deps(session, restaurant_id, persona)
    started = time.monotonic()
    result = await run_turn(state, deps)
    latency_ms = int((time.monotonic() - started) * 1000)

    session.add(
        ConversationTurn(
            restaurant_id=restaurant_id, conversation_id=conversation_id, seq=seq + 1,
            role=TurnRole.AGENT, content=result.reply, content_json=result.trace, latency_ms=latency_ms,
        )
    )
    if state.status == "escalated":
        conv.status = ConversationStatus.ESCALATED
    return result.reply, result.trace, conv.status


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
