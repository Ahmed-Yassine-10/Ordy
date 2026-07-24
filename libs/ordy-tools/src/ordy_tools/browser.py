"""BrowserAdapter — dispatches a verified workflow to the sandbox (doc 04 §6, ADR-011).

The API never runs a browser in-process: it hands a workflow id + bound parameters to
the isolated automation service. Combined with ``FallbackAdapter``, a drifted workflow
degrades to Ordy's own store instead of dropping the order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class AutomationDispatcher(Protocol):
    """Transport to the sandbox runner (Celery/HTTP in prod, fake in tests)."""

    async def run(
        self, workflow_id: str, params: dict, *, idempotency_key: str, platform_confirmed: bool
    ) -> dict: ...


class WorkflowUnavailable(RuntimeError):
    """No verified workflow backs this tool — the caller should fall back."""


class BrowserAdapter:
    name = "browser"

    def __init__(
        self,
        dispatcher: AutomationDispatcher,
        workflow_ids: dict[str, str],
        *,
        build_params: Callable[[str, dict], dict],
    ) -> None:
        self._dispatcher = dispatcher
        self._workflow_ids = workflow_ids
        self._build_params = build_params

    async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
        workflow_id = self._workflow_ids.get(tool_key)
        if not workflow_id:
            raise WorkflowUnavailable(f"no verified workflow for '{tool_key}'")

        result = await self._dispatcher.run(
            workflow_id,
            self._build_params(tool_key, args),
            idempotency_key=idempotency_key,
            # The action gate already confirmed with the customer; the sandbox refuses to
            # submit without this flag.
            platform_confirmed=True,
        )
        if not result.get("ok"):
            raise RuntimeError(
                f"automation failed: {result.get('error_code')} {result.get('error_message', '')}".strip()
            )

        captured = result.get("captured", {})
        if tool_key == "create_order":
            return {
                "order_id": str(captured.get("order_reference", "")),
                "status": "confirmed",
            }
        if tool_key == "make_reservation":
            return {"reservation_id": str(captured.get("reservation_reference", "")), "status": "confirmed"}
        return {"acknowledged": True}
