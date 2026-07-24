"""Tool catalog + per-tenant enablement (doc 07 §2.5).

Enabling a tool is a deliberate human act (manager+), recorded with who approved it.
Caps set here may only tighten platform defaults — the policy engine enforces that.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from ordy_core.enums import MemberRole, RiskLevel
from ordy_core.errors import NotFound
from ordy_core.models import RestaurantTool, ToolDefinition
from pydantic import BaseModel, Field
from sqlalchemy import select

from ordy_api.deps import Scope, require_tenant

router = APIRouter(prefix="/restaurants/{restaurant_id}", tags=["tools"])


class ToolOut(BaseModel):
    key: str
    version: int
    title: str
    description: str
    risk: RiskLevel
    requires_confirmation: bool
    enabled: bool
    adapter: str
    channels: list[str]
    caps: dict


class ToolUpdate(BaseModel):
    enabled: bool | None = None
    adapter: str | None = Field(default=None, pattern="^(native|rest|pos|browser)$")
    channels: list[str] | None = None
    caps: dict | None = None


def _rid(scope: Scope) -> uuid.UUID:
    assert scope.restaurant_id is not None
    return scope.restaurant_id


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(scope: Scope = Depends(require_tenant(MemberRole.VIEWER))) -> list[ToolOut]:
    """Full platform catalog with this tenant's enablement state (unbound = disabled)."""
    definitions = list(await scope.session.scalars(select(ToolDefinition).where(ToolDefinition.is_active.is_(True))))
    bindings = {
        b.tool_definition_id: b
        for b in await scope.session.scalars(
            select(RestaurantTool).where(RestaurantTool.restaurant_id == _rid(scope))
        )
    }
    out: list[ToolOut] = []
    for definition in definitions:
        binding = bindings.get(definition.id)
        out.append(
            ToolOut(
                key=definition.key,
                version=definition.version,
                title=definition.title,
                description=definition.description,
                risk=definition.risk,
                requires_confirmation=definition.requires_confirmation,
                enabled=bool(binding and binding.enabled),
                adapter=binding.adapter if binding else "native",
                channels=list(binding.channels) if binding else [],
                caps=dict(binding.caps) if binding else {},
            )
        )
    return out


@router.put("/tools/{tool_key}", response_model=ToolOut)
async def update_tool(
    tool_key: str, body: ToolUpdate, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> ToolOut:
    definition = await scope.session.scalar(
        select(ToolDefinition).where(ToolDefinition.key == tool_key).order_by(ToolDefinition.version.desc()).limit(1)
    )
    if definition is None:
        raise NotFound(f"tool '{tool_key}' is not in the platform catalog")

    binding = await scope.session.scalar(
        select(RestaurantTool).where(
            RestaurantTool.restaurant_id == _rid(scope),
            RestaurantTool.tool_definition_id == definition.id,
        )
    )
    if binding is None:
        binding = RestaurantTool(restaurant_id=_rid(scope), tool_definition_id=definition.id)
        scope.session.add(binding)

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(binding, field, value)
    if changes.get("enabled"):
        binding.approved_by = scope.principal.user_id
        binding.approved_at = datetime.now(UTC)
    await scope.session.flush()

    return ToolOut(
        key=definition.key,
        version=definition.version,
        title=definition.title,
        description=definition.description,
        risk=definition.risk,
        requires_confirmation=definition.requires_confirmation,
        enabled=binding.enabled,
        adapter=binding.adapter,
        channels=list(binding.channels),
        caps=dict(binding.caps),
    )
