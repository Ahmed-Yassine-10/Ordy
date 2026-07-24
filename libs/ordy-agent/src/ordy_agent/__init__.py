"""ordy-agent — the conversational brain (doc 03).

Phase 5 wires the Conversation + Knowledge roles for read-only Q&A. The Planning /
Validation / Execution roles (tool calling, confirmation interrupts) land in Phase 6,
at which point the LangGraph runtime in ``graph.py`` becomes the primary driver. The
node logic here is framework-independent and testable with a deterministic brain.
"""

from ordy_agent.brain import AgentBrain, RuleBasedBrain
from ordy_agent.deps import AgentDeps
from ordy_agent.engine import TurnResult, run_turn
from ordy_agent.router import ModelRouter, ModelTier
from ordy_agent.state import ConversationState, Intent, Turn

__all__ = [
    "AgentBrain",
    "AgentDeps",
    "ConversationState",
    "Intent",
    "ModelRouter",
    "ModelTier",
    "RuleBasedBrain",
    "Turn",
    "TurnResult",
    "run_turn",
]
