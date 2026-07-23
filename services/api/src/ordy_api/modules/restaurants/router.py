from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from ordy_core.enums import MemberRole
from ordy_core.errors import Unauthenticated

from ordy_api.deps import Scope, get_scope, require_tenant
from ordy_api.modules.restaurants import service
from ordy_api.modules.restaurants.schemas import (
    MemberInvite,
    MemberOut,
    RestaurantCreate,
    RestaurantOut,
    RestaurantSummary,
    RestaurantUpdate,
)

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


def _require_user(scope: Scope) -> uuid.UUID:
    if scope.principal.user_id is None:
        raise Unauthenticated("this endpoint requires a user session")
    return scope.principal.user_id


@router.post("", response_model=RestaurantOut, status_code=status.HTTP_201_CREATED)
async def create_restaurant(
    body: RestaurantCreate, scope: Scope = Depends(get_scope)
) -> RestaurantOut:
    owner_id = _require_user(scope)
    restaurant = await service.create_restaurant(
        scope.session,
        owner_id=owner_id,
        name=body.name,
        timezone=body.timezone,
        currency=body.currency,
        default_language=body.default_language,
    )
    return RestaurantOut.model_validate(restaurant, from_attributes=True)


@router.get("", response_model=list[RestaurantSummary])
async def list_my_restaurants(scope: Scope = Depends(get_scope)) -> list[RestaurantSummary]:
    user_id = _require_user(scope)
    pairs = await service.list_for_user(scope.session, user_id=user_id)
    return [
        RestaurantSummary(
            **RestaurantOut.model_validate(r, from_attributes=True).model_dump(), role=role
        )
        for r, role in pairs
    ]


@router.get("/{restaurant_id}", response_model=RestaurantOut)
async def get_restaurant(scope: Scope = Depends(require_tenant(MemberRole.VIEWER))) -> RestaurantOut:
    restaurant = await service.get(scope.session, scope.restaurant_id)  # type: ignore[arg-type]
    return RestaurantOut.model_validate(restaurant, from_attributes=True)


@router.patch("/{restaurant_id}", response_model=RestaurantOut)
async def update_restaurant(
    body: RestaurantUpdate, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> RestaurantOut:
    changes = body.model_dump(exclude_unset=True)
    restaurant = await service.update(scope.session, scope.restaurant_id, changes)  # type: ignore[arg-type]
    return RestaurantOut.model_validate(restaurant, from_attributes=True)


@router.get("/{restaurant_id}/members", response_model=list[MemberOut])
async def list_members(
    scope: Scope = Depends(require_tenant(MemberRole.VIEWER)),
) -> list[MemberOut]:
    pairs = await service.list_members(scope.session, scope.restaurant_id)  # type: ignore[arg-type]
    return [
        MemberOut(user_id=u.id, email=u.email, name=u.name, role=role) for u, role in pairs
    ]


@router.post(
    "/{restaurant_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED
)
async def invite_member(
    body: MemberInvite, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> MemberOut:
    user, role = await service.invite_member(
        scope.session, scope.restaurant_id, email=body.email, role=body.role  # type: ignore[arg-type]
    )
    return MemberOut(user_id=user.id, email=user.email, name=user.name, role=role)
