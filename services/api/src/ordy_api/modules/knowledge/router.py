from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from ordy_core.db import TenantContext
from ordy_core.enums import MemberRole

from ordy_api.config import Settings, get_settings
from ordy_api.deps import Scope, require_tenant
from ordy_api.embedding import get_embedder
from ordy_api.modules.knowledge import service
from ordy_api.modules.knowledge.retrieval import hybrid_search
from ordy_api.modules.knowledge.schemas import (
    CapabilityMapOut,
    PublishResult,
    ReviewData,
    ReviewSubmit,
    RunOut,
    SearchHit,
    SearchRequest,
    SourceCreate,
    SourceOut,
)

router = APIRouter(prefix="/restaurants/{restaurant_id}", tags=["knowledge"])


def _rid(scope: Scope) -> uuid.UUID:
    assert scope.restaurant_id is not None
    return scope.restaurant_id


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> SourceOut:
    source = await service.create_source(
        scope.session, _rid(scope), kind=body.kind, config=body.config, schedule=body.schedule
    )
    return SourceOut.model_validate(source, from_attributes=True)


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(scope: Scope = Depends(require_tenant(MemberRole.VIEWER))) -> list[SourceOut]:
    sources = await service.list_sources(scope.session, _rid(scope))
    return [SourceOut.model_validate(s, from_attributes=True) for s in sources]


@router.post("/sources/{source_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    source_id: uuid.UUID,
    request: Request,
    scope: Scope = Depends(require_tenant(MemberRole.MANAGER)),
    settings: Settings = Depends(get_settings),
) -> RunOut:
    ctx = TenantContext(user_id=scope.principal.user_id, restaurant_id=_rid(scope))
    run = await service.trigger_run(request.app.state.db, ctx, settings, source_id=source_id)
    return RunOut.model_validate(run, from_attributes=True)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.VIEWER))
) -> RunOut:
    run = await service.get_run(scope.session, run_id)
    return RunOut.model_validate(run, from_attributes=True)


@router.get("/runs/{run_id}/review", response_model=ReviewData)
async def get_review(
    run_id: uuid.UUID, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> ReviewData:
    run, menu_draft, capability_map = await service.get_review(scope.session, run_id)
    return ReviewData(
        run=RunOut.model_validate(run, from_attributes=True),
        menu_draft=menu_draft,
        capability_map=capability_map,
        warnings=list(run.stats.get("warnings", [])),
    )


@router.post("/runs/{run_id}/review", response_model=PublishResult)
async def submit_review(
    run_id: uuid.UUID,
    body: ReviewSubmit,
    scope: Scope = Depends(require_tenant(MemberRole.MANAGER)),
) -> PublishResult:
    return await service.publish_review(
        scope.session, _rid(scope), run_id, body, user_id=scope.principal.user_id, embedder=get_embedder()
    )


@router.get("/capability-maps", response_model=list[CapabilityMapOut])
async def list_capability_maps(
    scope: Scope = Depends(require_tenant(MemberRole.VIEWER)),
) -> list[CapabilityMapOut]:
    maps = await service.list_capability_maps(scope.session, _rid(scope))
    return [CapabilityMapOut.model_validate(m, from_attributes=True) for m in maps]


@router.post("/knowledge/search", response_model=list[SearchHit])
async def knowledge_search(
    body: SearchRequest, scope: Scope = Depends(require_tenant(MemberRole.VIEWER))
) -> list[SearchHit]:
    """Debug/inspection retrieval: hybrid search over approved chunks, with provenance
    (doc 07 §2.3). The agent uses the same path internally from Phase 5."""
    hits = await hybrid_search(scope.session, _rid(scope), body.query, get_embedder(), k=body.k)
    return [SearchHit(**hit) for hit in hits]
