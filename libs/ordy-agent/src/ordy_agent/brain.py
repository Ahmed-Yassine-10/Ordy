"""The agent's language capability behind a port (ADR-008).

``AgentBrain`` exposes the role-level operations the nodes need. ``RuleBasedBrain`` is
a deterministic implementation for dev/CI/evals — no provider, fully reproducible.
``LLMBrain`` (prod) maps each operation to a model-router tier + a prompt template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ordy_rag.models import RetrievedChunk

from ordy_agent.router import ModelRouter, ModelTier
from ordy_agent.state import ConversationState, Intent

_GREETINGS = ("hello", "hi ", "hey", "bonjour", "salut", "aslema", "ahla", "أهلا", "سلام")
_HANDOFF = ("human", "manager", "someone", "a person", "waiter", "staff", "real person", "بشر")
_INQUIRE_HINTS = (
    "?", "how much", "price", "prix", "combien", "قداش", "menu", "have", "do you",
    "vegetarian", "végétarien", "vegan", "halal", "allerg", "hours", "open", "close",
    "deliver", "livraison", "spicy", "gluten", "recommend",
)


class AgentBrain(Protocol):
    async def classify_intent(self, text: str, history: list[str]) -> Intent: ...
    async def answer_from_knowledge(
        self, question: str, chunks: list[RetrievedChunk], persona: dict, language: str
    ) -> str: ...
    async def smalltalk(self, state: ConversationState, persona: dict, language: str) -> str: ...


class RuleBasedBrain:
    """Deterministic brain. Answers are built from retrieved context (so grounding
    holds) — good enough to exercise routing, retrieval, and grounding in tests."""

    async def classify_intent(self, text: str, history: list[str]) -> Intent:
        t = (text or "").lower()
        if any(h in t for h in _HANDOFF):
            return Intent.HANDOFF
        if any(h in t for h in _INQUIRE_HINTS):
            return Intent.INQUIRE
        if any(t.strip().startswith(g.strip()) or f" {g.strip()} " in f" {t} " for g in _GREETINGS):
            return Intent.SMALLTALK
        return Intent.INQUIRE  # default to trying to help

    async def answer_from_knowledge(
        self, question: str, chunks: list[RetrievedChunk], persona: dict, language: str
    ) -> str:
        if not chunks:
            return persona.get("unsure") or _localized(
                language,
                en="I'm not certain about that — let me connect you with a colleague.",
                fr="Je ne suis pas sûr de cela — je vous mets en relation avec un collègue.",
            )
        # Compose from the top chunks; content already carries item names + prices, so any
        # number in the reply is grounded by construction.
        body = _clean(chunks[0].content)
        lead = _localized(language, en="Here's what we have: ", fr="Voici ce que nous avons : ")
        return f"{lead}{body}"

    async def smalltalk(self, state: ConversationState, persona: dict, language: str) -> str:
        greeting = persona.get("greeting")
        if greeting:
            return greeting
        return _localized(
            language,
            en="Welcome! I can help with our menu, hours, and orders. What would you like?",
            fr="Bienvenue ! Je peux vous renseigner sur le menu, les horaires et les commandes. Que puis-je faire ?",
        )


def _clean(text: str) -> str:
    # Drop a leading heading line and collapse whitespace.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines and len(lines) > 1:
        lines = lines[1:]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _localized(language: str, *, en: str, fr: str) -> str:
    return fr if str(language).startswith("fr") else en


# --------- Production brain (LLM-backed) — wired with the model router; not exercised
# in the authoring env (no provider). ---------


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


class LLM(Protocol):
    async def complete(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.3) -> str: ...


class OpenAILLM:
    """Placeholder for the model-router-backed completion client (ADR-008)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def complete(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.3) -> str:
        raise NotImplementedError("wire the model-router completion client here")


@dataclass(slots=True)
class LLMBrain:
    """Maps brain operations to model-router tiers + prompts (prod). Grounding is still
    enforced by the deterministic checker in the engine, regardless of the model."""

    llm: LLM
    router: ModelRouter

    async def classify_intent(self, text: str, history: list[str]) -> Intent:
        raw = await self.llm.complete(
            [ChatMessage("system", "Classify the customer intent."), ChatMessage("user", text)],
            model=self.router.model_for(ModelTier.CLASSIFIER),
        )
        try:
            return Intent(raw.strip().lower())
        except ValueError:
            return Intent.INQUIRE

    async def answer_from_knowledge(
        self, question: str, chunks: list[RetrievedChunk], persona: dict, language: str
    ) -> str:
        from ordy_agent.prompts import knowledge_prompt

        messages = knowledge_prompt(question, chunks, persona, language)
        return await self.llm.complete(messages, model=self.router.model_for(ModelTier.CONVERSATION))

    async def smalltalk(self, state: ConversationState, persona: dict, language: str) -> str:
        from ordy_agent.prompts import smalltalk_prompt

        messages = smalltalk_prompt(state, persona, language)
        return await self.llm.complete(messages, model=self.router.model_for(ModelTier.CONVERSATION))
