from __future__ import annotations

import uuid

from ordy_core.enums import ProductStatus
from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    sort: int = 0


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    name_i18n: dict[str, str]
    description: str | None
    sort: int


class VariantIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price_minor: int = Field(ge=0)
    sort: int = 0
    is_available: bool = True


class VariantOut(VariantIn):
    id: uuid.UUID


class ProductCreate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    name_i18n: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    price_minor: int | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    variants: list[VariantIn] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: uuid.UUID | None = None
    description: str | None = None
    price_minor: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None
    allergens: list[str] | None = None
    is_available: bool | None = None
    status: ProductStatus | None = None


class ProductOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    name_i18n: dict[str, str]
    description: str | None
    price_minor: int | None
    currency: str
    tags: list[str]
    allergens: list[str]
    is_available: bool
    status: ProductStatus
    variants: list[VariantOut]


class AvailabilityUpdate(BaseModel):
    is_available: bool
