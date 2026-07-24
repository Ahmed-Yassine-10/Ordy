"""Browser workflow verification + approval (doc 07 §2.5).

A workflow may only go live after a dry-run passes AND a human approves it — the same
draft→review→publish discipline ingestion uses for prices (ADR-012).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from ordy_automation.drift import WorkflowHealth, record_verification
from ordy_core.enums import MemberRole, WorkflowStatus
from ordy_core.errors import NotFound, ValidationFailed
from ordy_core.models import AutomationRun, AutomationWorkflow
from pydantic import BaseModel
from sqlalchemy import select

from ordy_api.deps import Scope, require_tenant

router = APIRouter(prefix="/restaurants/{restaurant_id}", tags=["workflows"])


class WorkflowOut(BaseModel):
    id: uuid.UUID
    action_key: str
    target_domain: str
    version: int
    status: WorkflowStatus
    failure_count: int
    last_verified_at: datetime | None
    step_count: int


class RunOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    artifacts_prefix: str | None
    error: dict | None


def _rid(scope: Scope) -> uuid.UUID:
    assert scope.restaurant_id is not None
    return scope.restaurant_id


def _out(workflow: AutomationWorkflow) -> WorkflowOut:
    steps = (workflow.definition or {}).get("steps", [])
    return WorkflowOut(
        id=workflow.id,
        action_key=workflow.action_key,
        target_domain=workflow.target_domain,
        version=workflow.version,
        status=workflow.status,
        failure_count=workflow.failure_count,
        last_verified_at=workflow.last_verified_at,
        step_count=len(steps),
    )


async def _load(scope: Scope, workflow_id: uuid.UUID) -> AutomationWorkflow:
    workflow = await scope.session.get(AutomationWorkflow, workflow_id)
    if workflow is None or workflow.restaurant_id != _rid(scope):
        raise NotFound("workflow not found")
    return workflow


@router.get("/workflows", response_model=list[WorkflowOut])
async def list_workflows(scope: Scope = Depends(require_tenant(MemberRole.VIEWER))) -> list[WorkflowOut]:
    rows = await scope.session.scalars(
        select(AutomationWorkflow)
        .where(AutomationWorkflow.restaurant_id == _rid(scope))
        .order_by(AutomationWorkflow.created_at.desc())
    )
    return [_out(w) for w in rows]


@router.post("/workflows/{workflow_id}/verify", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def verify_workflow(
    workflow_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> RunOut:
    """Queue a sandbox dry-run. It stops before the final submit, so verification never
    places a real order."""
    workflow = await _load(scope, workflow_id)
    workflow.status = WorkflowStatus.VERIFYING

    run = AutomationRun(
        restaurant_id=_rid(scope),
        workflow_id=workflow.id,
        kind="verification",
        status="queued",
        artifacts_prefix=f"t/{_rid(scope)}/automation/{workflow.id}",
        started_at=datetime.now(UTC),
    )
    scope.session.add(run)
    await scope.session.flush()
    # Dispatch to the sandbox service happens on the automation queue; the run row is the
    # handle the dashboard polls for the replay + screenshots.
    return RunOut(id=run.id, kind=run.kind, status=run.status, artifacts_prefix=run.artifacts_prefix, error=None)


@router.post("/workflows/{workflow_id}/approve", response_model=WorkflowOut)
async def approve_workflow(
    workflow_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> WorkflowOut:
    """Approve a VERIFIED workflow for live traffic. A draft or failed workflow cannot be
    approved — verification is not optional."""
    workflow = await _load(scope, workflow_id)
    if workflow.status is not WorkflowStatus.VERIFIED:
        raise ValidationFailed(
            f"workflow must pass verification before approval (status={workflow.status.value})"
        )
    workflow.status = WorkflowStatus.ACTIVE
    workflow.approved_by = scope.principal.user_id
    workflow.approved_at = datetime.now(UTC)
    return _out(workflow)


@router.post("/workflows/{workflow_id}/disable", response_model=WorkflowOut)
async def disable_workflow(
    workflow_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> WorkflowOut:
    """Kill switch — orders immediately fall back to Ordy's own store."""
    workflow = await _load(scope, workflow_id)
    health = record_verification(
        WorkflowHealth(status=workflow.status, failure_count=workflow.failure_count), passed=False
    )
    workflow.status = health.status
    return _out(workflow)
