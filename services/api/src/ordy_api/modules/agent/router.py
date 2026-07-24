from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from ordy_core.enums import MemberRole

from ordy_api.deps import Scope, require_tenant
from ordy_api.modules.agent import service
from ordy_api.modules.agent.schemas import (
    AgentConfigOut,
    AgentConfigUpdate,
    ConversationOut,
    ConversationRef,
    TurnOut,
    TurnRequest,
    TurnResponse,
)

router = APIRouter(prefix="/restaurants/{restaurant_id}", tags=["agent"])


def _rid(scope: Scope) -> uuid.UUID:
    assert scope.restaurant_id is not None
    return scope.restaurant_id


@router.get("/agent-config", response_model=AgentConfigOut)
async def get_config(scope: Scope = Depends(require_tenant(MemberRole.VIEWER))) -> AgentConfigOut:
    cfg = await service.get_or_create_config(scope.session, _rid(scope))
    return AgentConfigOut.model_validate(cfg, from_attributes=True)


@router.patch("/agent-config", response_model=AgentConfigOut)
async def update_config(
    body: AgentConfigUpdate, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> AgentConfigOut:
    cfg = await service.update_config(scope.session, _rid(scope), body.model_dump(exclude_unset=True))
    return AgentConfigOut.model_validate(cfg, from_attributes=True)


@router.post("/sandbox/conversations", response_model=ConversationRef, status_code=status.HTTP_201_CREATED)
async def start_sandbox(scope: Scope = Depends(require_tenant(MemberRole.STAFF))) -> ConversationRef:
    conv = await service.create_conversation(scope.session, _rid(scope))
    return ConversationRef(conversation_id=conv.id, language=conv.language or "fr")


@router.post("/sandbox/conversations/{conversation_id}/turns", response_model=TurnResponse)
async def sandbox_turn(
    conversation_id: uuid.UUID,
    body: TurnRequest,
    scope: Scope = Depends(require_tenant(MemberRole.STAFF)),
) -> TurnResponse:
    reply, trace, conv_status = await service.post_turn(
        scope.session, _rid(scope), conversation_id, body.text
    )
    return TurnResponse(reply=reply, trace=trace, status=conv_status)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.VIEWER))
) -> ConversationOut:
    conv, turns = await service.get_conversation_with_turns(scope.session, _rid(scope), conversation_id)
    return ConversationOut(
        id=conv.id,
        channel=conv.channel.value,
        language=conv.language,
        status=conv.status,
        outcome=conv.outcome,
        turns=[
            TurnOut(seq=t.seq, role=t.role.value, content=t.content, latency_ms=t.latency_ms, created_at=t.created_at)
            for t in turns
        ],
    )
