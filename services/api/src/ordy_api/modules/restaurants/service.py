from __future__ import annotations

import re
import secrets
import uuid

from ordy_core.enums import MemberRole
from ordy_core.errors import Conflict, NotFound
from ordy_core.models import Restaurant, RestaurantMember, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "restaurant"
    return f"{base}-{secrets.token_hex(3)}"


async def create_restaurant(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    name: str,
    timezone: str,
    currency: str,
    default_language: str,
) -> Restaurant:
    restaurant = Restaurant(
        slug=_slugify(name),
        name=name,
        timezone=timezone,
        currency=currency.upper(),
        default_language=default_language,
    )
    session.add(restaurant)
    await session.flush()  # assign id before creating the owner membership
    session.add(
        RestaurantMember(
            restaurant_id=restaurant.id, user_id=owner_id, role=MemberRole.OWNER
        )
    )
    await session.flush()
    return restaurant


async def list_for_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[tuple[Restaurant, MemberRole]]:
    rows = await session.execute(
        select(Restaurant, RestaurantMember.role)
        .join(RestaurantMember, RestaurantMember.restaurant_id == Restaurant.id)
        .where(RestaurantMember.user_id == user_id, Restaurant.deleted_at.is_(None))
        .order_by(Restaurant.created_at.desc())
    )
    return [(r, role) for r, role in rows.all()]


async def get(session: AsyncSession, restaurant_id: uuid.UUID) -> Restaurant:
    restaurant = await session.get(Restaurant, restaurant_id)
    if restaurant is None or restaurant.deleted_at is not None:
        raise NotFound("restaurant not found")
    return restaurant


async def update(
    session: AsyncSession, restaurant_id: uuid.UUID, changes: dict[str, object]
) -> Restaurant:
    restaurant = await get(session, restaurant_id)
    for field, value in changes.items():
        setattr(restaurant, field, value)
    await session.flush()
    return restaurant


async def list_members(
    session: AsyncSession, restaurant_id: uuid.UUID
) -> list[tuple[User, MemberRole]]:
    rows = await session.execute(
        select(User, RestaurantMember.role)
        .join(RestaurantMember, RestaurantMember.user_id == User.id)
        .where(RestaurantMember.restaurant_id == restaurant_id)
        .order_by(RestaurantMember.created_at)
    )
    return [(u, role) for u, role in rows.all()]


async def invite_member(
    session: AsyncSession, restaurant_id: uuid.UUID, *, email: str, role: MemberRole
) -> tuple[User, MemberRole]:
    # Phase 2: invite an already-registered user. Email-based signup invites land in
    # a later phase; this satisfies the onboarding exit-criteria flow.
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise NotFound("no Ordy user with that email — ask them to sign up first")
    existing = await session.scalar(
        select(RestaurantMember.role).where(
            RestaurantMember.restaurant_id == restaurant_id,
            RestaurantMember.user_id == user.id,
        )
    )
    if existing is not None:
        raise Conflict("user is already a member of this restaurant")
    session.add(
        RestaurantMember(restaurant_id=restaurant_id, user_id=user.id, role=role)
    )
    await session.flush()
    return user, role
