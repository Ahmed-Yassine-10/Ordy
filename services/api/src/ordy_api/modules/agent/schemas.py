from __future__ import annotations

import uuid
from datetime import datetime

from ordy_core.enums import ConversationStatus
from pydantic import BaseModel, Field


class AgentConfigOut(BaseModel):
    id: uuid.UUID
    name: str
    persona: dict
    voice: dict
    languages: list[str]
    escalation: dict
    is_active: bool


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    persona: dict | None = None
    voice: dict | None = None
    languages: list[str] | None = None
    escalation: dict | None = None


class ConversationRef(BaseModel):
    conversation_id: uuid.UUID
    language: str


class TurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TurnResponse(BaseModel):
    reply: str
    trace: dict  # route, intent, retrieved (with provenance), grounding
    status: ConversationStatus


class TurnOut(BaseModel):
    seq: int
    role: str
    content: str | None
    latency_ms: int | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    channel: str
    language: str | None
    status: ConversationStatus
    outcome: str | None
    turns: list[TurnOut] = []
