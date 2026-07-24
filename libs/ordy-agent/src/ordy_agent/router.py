"""Model router (ADR-008): named tiers → concrete provider+model IDs, per-tenant
overridable. No model ID appears in node logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModelTier(StrEnum):
    REALTIME_SPEECH = "realtime_speech"
    CONVERSATION = "conversation"
    PLANNING = "planning"
    EXTRACTION = "extraction"
    CLASSIFIER = "classifier"
    EMBEDDING = "embedding"


# Launch mapping (ADR-008). Concrete IDs live in config/model_router.yaml in prod; this
# is the default the API/config layer overrides. Placeholders documented, not hardcoded
# into calls.
_DEFAULTS: dict[ModelTier, str] = {
    ModelTier.CONVERSATION: "openai:gpt-conversation",
    ModelTier.PLANNING: "openai:gpt-planning",
    ModelTier.EXTRACTION: "openai:gpt-extraction",
    ModelTier.CLASSIFIER: "openai:gpt-classifier",
    ModelTier.EMBEDDING: "openai:text-embedding",
    ModelTier.REALTIME_SPEECH: "openai:gpt-realtime",
}


@dataclass(slots=True)
class ModelRouter:
    overrides: dict[ModelTier, str] | None = None

    def model_for(self, tier: ModelTier) -> str:
        if self.overrides and tier in self.overrides:
            return self.overrides[tier]
        return _DEFAULTS[tier]
