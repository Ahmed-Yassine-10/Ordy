"""Typed conversation state (doc 03 §2). Structured fields survive compaction; prices
live in structured data, never inferred from prose."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from ordy_rag.models import RetrievedChunk


class Intent(StrEnum):
    INQUIRE = "inquire"
    SMALLTALK = "smalltalk"
    HANDOFF = "handoff"
    # Reserved for Phase 6 (tool calling). The Phase 5 engine routes these to knowledge.
    ORDER = "order"
    RESERVE = "reserve"
    MODIFY = "modify"
    CANCEL = "cancel"


@dataclass(slots=True)
class Turn:
    role: str  # customer | agent | system
    content: str
    seq: int


@dataclass(slots=True)
class ConversationState:
    conversation_id: uuid.UUID
    restaurant_id: uuid.UUID
    channel: str = "sandbox"  # sandbox | text_widget | voice_web | voice_phone
    language: str = "fr"

    turns: list[Turn] = field(default_factory=list)
    summary: str | None = None
    intent: Intent | None = None
    retrieval_context: list[RetrievedChunk] = field(default_factory=list)
    facts_established: list[str] = field(default_factory=list)
    status: str = "active"  # active | escalated | completed
    # Serialized ConfirmationRequest awaiting the customer's yes/no (doc 03 §4.2).
    # Kept as a dict so it survives persistence + state rebuild between turns.
    pending_confirmation: dict | None = None

    def last_user(self) -> str | None:
        for turn in reversed(self.turns):
            if turn.role == "customer":
                return turn.content
        return None

    def add_turn(self, role: str, content: str) -> Turn:
        turn = Turn(role=role, content=content, seq=len(self.turns))
        self.turns.append(turn)
        return turn
