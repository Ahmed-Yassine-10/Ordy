"""LangGraph runtime (ADR-004).

The five-role graph with durable checkpointing (Postgres) and the customer-confirmation
``interrupt`` becomes primary in Phase 6, where Planning → Validation → Execution need
it. For Phase 5's read-only flow the same logic runs via ``engine.run_turn``; this
assembles it as a single node so the graph plumbing exists and can be split later.

Importing this module does not require langgraph; ``build_graph`` does.
"""

from __future__ import annotations

from ordy_agent.deps import AgentDeps
from ordy_agent.engine import run_turn


def build_graph(deps: AgentDeps):  # type: ignore[no-untyped-def]
    from langgraph.graph import END, StateGraph  # optional 'graph' extra

    graph = StateGraph(dict)

    async def respond(payload: dict) -> dict:
        result = await run_turn(payload["state"], deps)
        return {"state": result.state, "reply": result.reply, "trace": result.trace}

    graph.add_node("respond", respond)
    graph.set_entry_point("respond")
    graph.add_edge("respond", END)
    return graph.compile()
