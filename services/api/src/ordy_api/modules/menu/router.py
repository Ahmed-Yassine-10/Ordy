from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from ordy_core.enums import MemberRole

from ordy_api.deps import Scope, require_tenant
from ordy_api.modules.menu import service
from ordy_api.modules.menu.schemas import (
    AvailabilityUpdate,
    CategoryCreate,
    CategoryOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

# Nested under a restaurant so require_tenant can read the {restaurant_id} path param.
router = APIRouter(prefix="/restaurants/{restaurant_id}/menu", tags=["menu"])


def _rid(scope: Scope) -> uuid.UUID:
    assert scope.restaurant_id is not None  # guaranteed by require_tenant
    return scope.restaurant_id


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    scope: Scope = Depends(require_tenant(MemberRole.VIEWER)),
) -> list[CategoryOut]:
    cats = await service.list_categories(scope.session, _rid(scope))
    return [CategoryOut.model_validate(c, from_attributes=True) for c in cats]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> CategoryOut:
    cat = await service.create_category(scope.session, _rid(scope), body.model_dump())
    return CategoryOut.model_validate(cat, from_attributes=True)


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    scope: Scope = Depends(require_tenant(MemberRole.VIEWER)),
) -> list[ProductOut]:
    products = await service.list_products(scope.session, _rid(scope))
    return [ProductOut.model_validate(p, from_attributes=True) for p in products]


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate, scope: Scope = Depends(require_tenant(MemberRole.MANAGER))
) -> ProductOut:
    data = body.model_dump()
    data["variants"] = [v for v in data.get("variants", [])]
    product = await service.create_product(scope.session, _rid(scope), data)
    return ProductOut.model_validate(product, from_attributes=True)


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    scope: Scope = Depends(require_tenant(MemberRole.MANAGER)),
) -> ProductOut:
    product = await service.update_product(
        scope.session, _rid(scope), product_id, body.model_dump(exclude_unset=True)
    )
    return ProductOut.model_validate(product, from_attributes=True)


@router.post("/products/{product_id}/availability", response_model=ProductOut)
async def set_availability(
    product_id: uuid.UUID,
    body: AvailabilityUpdate,
    scope: Scope = Depends(require_tenant(MemberRole.STAFF)),
) -> ProductOut:
    product = await service.update_product(
        scope.session, _rid(scope), product_id, {"is_available": body.is_available}
    )
    return ProductOut.model_validate(product, from_attributes=True)
