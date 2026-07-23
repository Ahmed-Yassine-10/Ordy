"""Seed the demo restaurant — "Pizza Rustica Sfax" — with an owner and a small menu.

    python -m ordy_api.scripts.seed_demo

Idempotent-ish: skips if the demo owner already exists. Runs as the app role but
uses a platform-admin context to write across tables (the seeding path).
"""

from __future__ import annotations

import asyncio

from ordy_core.db import Database, TenantContext
from ordy_core.enums import MemberRole, MenuStatus, ProductStatus
from ordy_core.models import (
    Menu,
    MenuCategory,
    Product,
    ProductVariant,
    Restaurant,
    RestaurantMember,
    User,
)
from ordy_security import hash_password
from sqlalchemy import select

from ordy_api.config import get_settings

DEMO_EMAIL = "owner@pizzarustica.tn"
DEMO_PASSWORD = "demo-password-123"


async def _seed(db: Database) -> None:
    admin_ctx = TenantContext(is_platform_admin=True)

    async with db.session(admin_ctx) as session:
        existing = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing is not None:
            print("demo owner already exists — nothing to do")
            return

        owner = User(
            email=DEMO_EMAIL,
            name="Rustica Owner",
            locale="fr",
            password_hash=hash_password(DEMO_PASSWORD),
        )
        session.add(owner)
        await session.flush()

        restaurant = Restaurant(
            slug="pizza-rustica-sfax",
            name="Pizza Rustica Sfax",
            timezone="Africa/Tunis",
            currency="TND",
            default_language="fr",
            languages=["fr", "en", "ar-TN"],
        )
        session.add(restaurant)
        await session.flush()

        session.add(
            RestaurantMember(
                restaurant_id=restaurant.id, user_id=owner.id, role=MemberRole.OWNER
            )
        )

        menu = Menu(restaurant_id=restaurant.id, status=MenuStatus.PUBLISHED)
        session.add(menu)
        await session.flush()

        pizzas = MenuCategory(restaurant_id=restaurant.id, menu_id=menu.id, name="Pizzas", sort=0)
        session.add(pizzas)
        await session.flush()

        pepperoni = Product(
            restaurant_id=restaurant.id,
            category_id=pizzas.id,
            name="Pizza Pepperoni",
            currency="TND",
            tags=["popular"],
            status=ProductStatus.PUBLISHED,
        )
        session.add(pepperoni)
        await session.flush()
        session.add_all(
            [
                ProductVariant(
                    restaurant_id=restaurant.id,
                    product_id=pepperoni.id,
                    name="Medium",
                    price_minor=24_000,  # 24.000 TND
                    sort=0,
                ),
                ProductVariant(
                    restaurant_id=restaurant.id,
                    product_id=pepperoni.id,
                    name="Large",
                    price_minor=32_000,  # 32.000 TND
                    sort=1,
                ),
            ]
        )

    print("seeded 'Pizza Rustica Sfax'")
    print(f"  owner login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


async def _main() -> None:
    settings = get_settings()
    db = Database(settings.database_url)
    try:
        await _seed(db)
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
