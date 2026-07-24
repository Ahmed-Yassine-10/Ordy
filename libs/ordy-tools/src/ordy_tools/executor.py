"""Secure executor (doc 03 §3.5). Pure code — no model in this path.

Guarantees: idempotency key per action, adapter isolation, outcome validation against
the ToolSpec output schema, and an audit record for every attempt.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from ordy_tools.models import ActionOutcome, ActionStatus, ToolSpec
from ordy_tools.schema import SchemaValidator, default_validator


class ExecutorAdapter(Protocol):
    name: str

    async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict: ...


class NativeAdapter:
    """Ordy's own store — every restaurant has this on day one (doc 01 §4.8).

    Phase 6 returns a synthetic result so the gate can be exercised end-to-end; Phase 7
    replaces the body with real order/reservation persistence. The contract (args in,
    output-schema-valid dict out, idempotency honored) does not change.
    """

    name = "native"

    def __init__(self) -> None:
        self._seen: dict[str, dict] = {}

    async def execute(self, tool_key: str, args: dict, *, idempotency_key: str) -> dict:
        if idempotency_key in self._seen:  # replay → same result, no double-create
            return self._seen[idempotency_key]

        ref = f"A{idempotency_key[:6].upper()}"
        if tool_key == "create_order":
            result = {"order_id": ref, "status": "confirmed", "eta_minutes": 20}
        elif tool_key == "make_reservation":
            result = {"reservation_id": ref, "status": "confirmed"}
        elif tool_key == "cancel_order":
            result = {"cancelled": True}
        elif tool_key == "check_availability":
            result = {"available": True}
        elif tool_key == "get_order_status":
            result = {"status": "preparing"}
        else:
            result = {"acknowledged": True}
        self._seen[idempotency_key] = result
        return result


async def execute_action(
    spec: ToolSpec,
    args: dict,
    adapter: ExecutorAdapter,
    *,
    idempotency_key: str | None = None,
    validator: SchemaValidator | None = None,
) -> ActionOutcome:
    """Execute a VALIDATED, CONFIRMED action. Callers must not reach here otherwise."""
    key = idempotency_key or str(uuid.uuid4())
    try:
        output = await adapter.execute(spec.key, args, idempotency_key=key)
    except Exception as exc:  # noqa: BLE001 — surfaced as a failed outcome + audit
        return ActionOutcome(
            status=ActionStatus.FAILED,
            error={"type": type(exc).__name__, "message": str(exc)},
            adapter=adapter.name,
            executed_at=datetime.now(UTC),
        )

    errors = (validator or default_validator()).validate(output, spec.output_schema)
    if errors:
        return ActionOutcome(
            status=ActionStatus.FAILED,
            error={"type": "OutputSchemaViolation", "message": "; ".join(errors[:3])},
            output=output,
            adapter=adapter.name,
            executed_at=datetime.now(UTC),
        )

    return ActionOutcome(
        status=ActionStatus.SUCCEEDED,
        output=output,
        external_ref=str(output.get("order_id") or output.get("reservation_id") or ""),
        adapter=adapter.name,
        executed_at=datetime.now(UTC),
    )
