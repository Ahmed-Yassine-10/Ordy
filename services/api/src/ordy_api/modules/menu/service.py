"""Menu service. Every query is implicitly tenant-scoped by RLS; we also pass
``restaurant_id`` explicitly (defense in depth, doc 08 §3)."""

from __future__ import annotations

import uuid

from ordy_core.enums import MenuStatus
from ordy_core.errors import NotFound
from ordy_core.models import Menu, MenuCategory, Product, ProductVariant, Restaurant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


async def _default_menu(session: AsyncSession, restaurant_id: uuid.UUID) -> Menu:
    """Every restaurant has one working menu in Phase 2; create on first use."""
    menu = await session.scalar(select(Menu).where(Menu.restaurant_id == restaurant_id).limit(1))
    if menu is None:
        menu = Menu(restaurant_id=restaurant_id, status=MenuStatus.DRAFT)
        session.add(menu)
        await session.flush()
    return menu


async def _currency(session: AsyncSession, restaurant_id: uuid.UUID) -> str:
    currency = await session.scalar(
        select(Restaurant.currency).where(Restaurant.id == restaurant_id)
    )
    return currency or "TND"


async def create_category(
    session: AsyncSession, restaurant_id: uuid.UUID, data: dict
) -> MenuCategory:
    menu = await _default_menu(session, restaurant_id)
    category = MenuCategory(restaurant_id=restaurant_id, menu_id=menu.id, **data)
    session.add(category)
    await session.flush()
    return category


async def list_categories(
    session: AsyncSession, restaurant_id: uuid.UUID
) -> list[MenuCategory]:
    rows = await session.scalars(
        select(MenuCategory)
        .where(MenuCategory.restaurant_id == restaurant_id)
        .order_by(MenuCategory.sort, MenuCategory.name)
    )
    return list(rows)


async def create_product(
    session: AsyncSession, restaurant_id: uuid.UUID, data: dict
) -> Product:
    variants = data.pop("variants", [])
    currency = await _currency(session, restaurant_id)
    product = Product(restaurant_id=restaurant_id, currency=currency, **data)
    session.add(product)
    await session.flush()
    for v in variants:
        session.add(ProductVariant(restaurant_id=restaurant_id, product_id=product.id, **v))
    await session.flush()
    return await get_product(session, restaurant_id, product.id)


async def get_product(
    session: AsyncSession, restaurant_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    product = await session.scalar(
        select(Product)
        .options(selectinload(Product.variants))
        .where(Product.id == product_id, Product.restaurant_id == restaurant_id)
    )
    if product is None:
        raise NotFound("product not found")
    return product


async def list_products(
    session: AsyncSession, restaurant_id: uuid.UUID
) -> list[Product]:
    rows = await session.scalars(
        select(Product)
        .options(selectinload(Product.variants))
        .where(Product.restaurant_id == restaurant_id)
        .order_by(Product.name)
    )
    return list(rows)


async def update_product(
    session: AsyncSession, restaurant_id: uuid.UUID, product_id: uuid.UUID, changes: dict
) -> Product:
    product = await get_product(session, restaurant_id, product_id)
    for field, value in changes.items():
        setattr(product, field, value)
    await session.flush()
    return product
