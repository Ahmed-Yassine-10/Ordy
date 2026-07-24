"""End-to-end action flow through the agent: plan → gate → confirmation → execution."""

from __future__ import annotations

import uuid

import pytest
from ordy_agent.brain import RuleBasedBrain
from ordy_agent.deps import AgentDeps
from ordy_agent.engine import run_turn
from ordy_agent.state import ConversationState
from ordy_agent.tools_runtime import ToolRuntime
from ordy_tools.policy import Caps, DeliveryPolicy, PolicyContext, ToolBinding
from ordy_tools.pricing import ProductSnapshot, VariantSnapshot

pytestmark = pytest.mark.asyncio

PEP = "11111111-1111-1111-1111-111111111111"
LARGE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEDIUM = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _runtime(**ctx_overrides) -> ToolRuntime:
    context = PolicyContext(
        channel="sandbox",
        currency="TND",
        bindings={"create_order": ToolBinding("create_order", enabled=True, channels=["sandbox"])},
        menu={
            PEP: ProductSnapshot(
                product_id=PEP, name="Pizza Pepperoni", currency="TND",
                variants={
                    LARGE: VariantSnapshot(LARGE, "Large", 32_000),
                    MEDIUM: VariantSnapshot(MEDIUM, "Medium", 24_000),
                },
            )
        },
        service_open={"pickup": True, "delivery": True, "dine_in": True, "reservation": True},
        delivery=DeliveryPolicy(in_zone=True, min_order_minor=25_000),
        caps=Caps(),
    )
    for key, value in ctx_overrides.items():
        setattr(context, key, value)
    return ToolRuntime(context=context)


def _deps(tools: ToolRuntime | None) -> AgentDeps:
    async def retrieve(q: str, k: int):
        return []

    return AgentDeps(brain=RuleBasedBrain(), retrieve=retrieve, persona={}, tools=tools)


def _state() -> ConversationState:
    return ConversationState(conversation_id=uuid.uuid4(), restaurant_id=uuid.uuid4(), language="en")


async def _say(state: ConversationState, deps: AgentDeps, text: str):
    state.add_turn("customer", text)
    return await run_turn(state, deps)


async def test_order_requires_confirmation_with_server_priced_summary() -> None:
    state, deps = _state(), _deps(_runtime())
    result = await _say(state, deps, "I want a large pepperoni pizza")

    assert result.trace["route"] == "action"
    assert result.trace["stage"] == "awaiting_confirmation"
    assert result.trace["validation"]["total_minor"] == 32_000
    assert "1× Pizza Pepperoni (Large)" in result.reply
    assert "32.000 TND" in result.reply
    assert state.pending_confirmation is not None  # gate is closed


async def test_confirmed_order_executes_once() -> None:
    state, deps = _state(), _deps(_runtime())
    await _say(state, deps, "I want a large pepperoni pizza")
    result = await _say(state, deps, "yes")

    assert result.trace["stage"] == "executed"
    assert result.trace["outcome"] == "succeeded"
    assert "Done" in result.reply
    assert state.pending_confirmation is None
    assert deps.tools.context.actions_taken == 1


async def test_declining_executes_nothing() -> None:
    state, deps = _state(), _deps(_runtime())
    await _say(state, deps, "I want a large pepperoni pizza")
    result = await _say(state, deps, "no")

    assert result.trace["stage"] == "declined"
    assert deps.tools.context.actions_taken == 0
    assert state.pending_confirmation is None


async def test_ambiguous_reply_keeps_the_gate_closed() -> None:
    state, deps = _state(), _deps(_runtime())
    await _say(state, deps, "I want a large pepperoni pizza")
    result = await _say(state, deps, "hmm, what's on it?")

    assert result.trace["stage"] == "awaiting_confirmation"
    assert state.pending_confirmation is not None  # still pending — no execution
    assert deps.tools.context.actions_taken == 0


async def test_missing_size_is_repaired_not_guessed() -> None:
    state, deps = _state(), _deps(_runtime())
    result = await _say(state, deps, "I want a pepperoni pizza")

    assert result.trace["stage"] == "rejected"
    assert result.trace["validation"]["rejection_code"] == "VARIANT_REQUIRED"
    assert "Large" in result.reply and "Medium" in result.reply  # agent asks


async def test_delivery_minimum_rejection_is_explained() -> None:
    state, deps = _state(), _deps(_runtime())
    # Medium (24.000) delivered is under the 25.000 minimum.
    result = await _say(state, deps, "I want a medium pepperoni pizza delivered")

    assert result.trace["stage"] == "rejected"
    assert result.trace["validation"]["rejection_code"] == "ORDER_BELOW_DELIVERY_MINIMUM"
    assert "25.000 TND" in result.reply


async def test_read_only_mode_never_proposes_actions() -> None:
    """With tools disabled (Phase 5 behavior) an order intent is answered, not executed."""
    state, deps = _state(), _deps(None)
    result = await _say(state, deps, "I want a large pepperoni pizza")
    assert result.trace["route"] == "knowledge"
