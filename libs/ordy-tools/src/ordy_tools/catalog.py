"""The platform ToolSpec catalog (doc 03 §4.1).

Tools ship via code review — never created at conversation time. A tenant enables a
subset (``restaurant_tools``); the model only ever sees enabled specs.
"""

from __future__ import annotations

from ordy_core.enums import RiskLevel

from ordy_tools.models import ToolSpec

_ITEM_SCHEMA = {
    "type": "object",
    "required": ["product_id", "quantity"],
    "additionalProperties": False,
    "properties": {
        "product_id": {"type": "string", "format": "uuid"},
        "variant_id": {"type": "string", "format": "uuid"},
        "quantity": {"type": "integer", "minimum": 1, "maximum": 20},
        "modifiers": {"type": "array", "items": {"type": "string", "format": "uuid"}},
        "note": {"type": "string", "maxLength": 200},
    },
}

CREATE_ORDER = ToolSpec(
    key="create_order",
    version=1,
    title="Create order",
    description="Place a new order for the current customer. Prices and totals are computed server-side.",
    risk=RiskLevel.FINANCIAL,
    requires_confirmation=True,
    idempotent=True,
    input_schema={
        "type": "object",
        "required": ["type", "items"],
        "additionalProperties": False,
        "properties": {
            "type": {"enum": ["pickup", "delivery", "dine_in"]},
            "items": {"type": "array", "minItems": 1, "maxItems": 30, "items": _ITEM_SCHEMA},
            "scheduled_for": {"type": "string"},
            "note": {"type": "string", "maxLength": 500},
        },
    },
    output_schema={
        "type": "object",
        "required": ["order_id", "status"],
        "properties": {
            "order_id": {"type": "string"},
            "status": {"enum": ["confirmed", "pending"]},
            "total_minor": {"type": "integer"},
            "currency": {"type": "string"},
            "eta_minutes": {"type": "integer"},
        },
    },
    validators=["items_available", "open_hours", "delivery_zone", "order_caps", "action_budget"],
    compensation={"tool": "cancel_order", "args_from_output": {"order_id": "order_id"}},
)

CHECK_AVAILABILITY = ToolSpec(
    key="check_availability",
    version=1,
    title="Check availability",
    description="Check whether a menu item is currently orderable.",
    risk=RiskLevel.READ,
    requires_confirmation=False,
    idempotent=True,
    input_schema={
        "type": "object",
        "required": ["product_id"],
        "additionalProperties": False,
        "properties": {
            "product_id": {"type": "string", "format": "uuid"},
            "variant_id": {"type": "string", "format": "uuid"},
        },
    },
    output_schema={
        "type": "object",
        "required": ["available"],
        "properties": {"available": {"type": "boolean"}, "reason": {"type": "string"}},
    },
    validators=["action_budget"],
)

MAKE_RESERVATION = ToolSpec(
    key="make_reservation",
    version=1,
    title="Make reservation",
    description="Book a table for a given party size and time.",
    risk=RiskLevel.WRITE,
    requires_confirmation=True,
    idempotent=True,
    input_schema={
        "type": "object",
        "required": ["party_size", "starts_at"],
        "additionalProperties": False,
        "properties": {
            "party_size": {"type": "integer", "minimum": 1, "maximum": 40},
            "starts_at": {"type": "string", "minLength": 4},
            "note": {"type": "string", "maxLength": 300},
        },
    },
    output_schema={
        "type": "object",
        "required": ["reservation_id", "status"],
        "properties": {
            "reservation_id": {"type": "string"},
            "status": {"enum": ["confirmed", "pending"]},
        },
    },
    validators=["reservation_rules", "action_budget"],
    compensation={"tool": "cancel_reservation", "args_from_output": {"reservation_id": "reservation_id"}},
)

REQUEST_HUMAN_HANDOFF = ToolSpec(
    key="request_human_handoff",
    version=1,
    title="Request human handoff",
    description="Escalate the conversation to restaurant staff.",
    risk=RiskLevel.READ,
    requires_confirmation=False,
    idempotent=True,
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {"reason": {"type": "string", "maxLength": 300}},
    },
    output_schema={"type": "object", "properties": {"acknowledged": {"type": "boolean"}}},
    validators=[],
)

GET_ORDER_STATUS = ToolSpec(
    key="get_order_status",
    version=1,
    title="Get order status",
    description="Look up the status of an existing order.",
    risk=RiskLevel.READ,
    requires_confirmation=False,
    idempotent=True,
    input_schema={
        "type": "object",
        "required": ["order_ref"],
        "additionalProperties": False,
        "properties": {"order_ref": {"type": "string", "maxLength": 64}},
    },
    output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
    validators=["action_budget"],
)

CANCEL_ORDER = ToolSpec(
    key="cancel_order",
    version=1,
    title="Cancel order",
    description="Cancel an existing order.",
    risk=RiskLevel.WRITE,
    requires_confirmation=True,
    idempotent=True,
    input_schema={
        "type": "object",
        "required": ["order_ref"],
        "additionalProperties": False,
        "properties": {"order_ref": {"type": "string", "maxLength": 64}, "reason": {"type": "string", "maxLength": 300}},
    },
    output_schema={"type": "object", "properties": {"cancelled": {"type": "boolean"}}},
    validators=["action_budget"],
)

PLATFORM_TOOLS: dict[str, ToolSpec] = {
    spec.key: spec
    for spec in (
        CREATE_ORDER,
        CHECK_AVAILABILITY,
        MAKE_RESERVATION,
        GET_ORDER_STATUS,
        CANCEL_ORDER,
        REQUEST_HUMAN_HANDOFF,
    )
}


def get_tool(key: str) -> ToolSpec | None:
    return PLATFORM_TOOLS.get(key)


def manifest(enabled_keys: list[str]) -> list[dict]:
    """Function definitions for the model — enabled tools only (doc 08 §6.2)."""
    return [PLATFORM_TOOLS[k].manifest_entry() for k in enabled_keys if k in PLATFORM_TOOLS]
