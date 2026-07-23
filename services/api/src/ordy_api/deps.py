"""Request dependencies: principal resolution → tenant context → RLS-scoped session.

Flow per request:
  1. ``get_scope`` resolves the principal (JWT user or API key), opens ONE
     transaction, and applies the user-level GUCs (``app.user_id`` /
     ``app.is_platform_admin``; API keys also pin ``app.restaurant_id``).
  2. ``require_tenant(min_role)`` verifies membership (readable thanks to the
     user-scoped RLS policy on ``restaurant_members``) and only then sets
     ``app.restaurant_id`` for the remainder of the transaction.

Tenant data is never queried before the matching GUC is set (doc 08 §3).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from fastapi import Depends, Path, Request
from ordy_core.db import Database, TenantContext, apply_tenant_context
from ordy_core.enums import MemberRole
from ordy_core.errors import Forbidden, Unauthenticated
from ordy_core.models import ApiKey, RestaurantMember
from ordy_security import decode_access_token, verify_api_key
from ordy_security.tokens import TokenError
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class Principal:
    kind: Literal["user", "api_key"]
    user_id: uuid.UUID | None = None
    is_platform_admin: bool = False
    restaurant_id: uuid.UUID | None = None  # API keys are tenant-bound
    scopes: tuple[str, ...] = ()


@dataclass(slots=True)
class Scope:
    """One request's DB session + who is acting. ``restaurant_id``/``role`` fill in
    once ``require_tenant`` has authorized a tenant."""

    session: AsyncSession
    principal: Principal
    restaurant_id: uuid.UUID | None = field(default=None)
    role: MemberRole | None = field(default=None)


def _get_db(request: Request) -> Database:
    return request.app.state.db


async def _resolve_api_key(db: Database, raw: str) -> Principal:
    prefix = raw[:16]
    # api_keys carry restaurant_id but the auth lookup precedes tenant context, so it
    # goes through a SECURITY DEFINER function that bypasses RLS (doc 06 §4, doc 08 §3).
    async with db.session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, restaurant_id, key_hash, scopes, expires_at "
                    "FROM app_api_key_candidates(:p)"
                ),
                {"p": prefix},
            )
        ).all()
        for row in rows:
            if verify_api_key(raw, bytes(row.key_hash)):
                await session.execute(
                    update(ApiKey).where(ApiKey.id == row.id).values(last_used_at=text("now()"))
                )
                return Principal(
                    kind="api_key",
                    restaurant_id=row.restaurant_id,
                    scopes=tuple(row.scopes or ()),
                )
    raise Unauthenticated("invalid API key")


async def _resolve_principal(request: Request, settings: Settings) -> Principal:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        try:
            claims = decode_access_token(
                auth[7:], secret=settings.jwt_secret, issuer=settings.jwt_issuer
            )
        except TokenError as exc:
            raise Unauthenticated("invalid or expired token") from exc
        return Principal(
            kind="user", user_id=claims.user_id, is_platform_admin=claims.is_platform_admin
        )

    api_key = request.headers.get("X-Api-Key")
    if api_key:
        return await _resolve_api_key(_get_db(request), api_key)

    raise Unauthenticated("missing credentials")


async def get_scope(
    request: Request, settings: Settings = Depends(get_settings)
) -> AsyncIterator[Scope]:
    principal = await _resolve_principal(request, settings)
    db = _get_db(request)
    async with db.session() as session:
        ctx = TenantContext(
            user_id=principal.user_id,
            is_platform_admin=principal.is_platform_admin,
            restaurant_id=principal.restaurant_id if principal.kind == "api_key" else None,
        )
        await apply_tenant_context(session, ctx)
        scope = Scope(session=session, principal=principal)
        if principal.kind == "api_key":
            scope.restaurant_id = principal.restaurant_id
        yield scope


def require_tenant(
    min_role: MemberRole = MemberRole.VIEWER,
) -> Callable[..., Awaitable[Scope]]:
    """Dependency factory: authorize the path's ``restaurant_id`` and pin RLS to it."""

    async def dependency(
        restaurant_id: uuid.UUID = Path(...), scope: Scope = Depends(get_scope)
    ) -> Scope:
        p = scope.principal
        if p.kind == "api_key":
            if p.restaurant_id != restaurant_id:
                raise Forbidden("API key is not valid for this restaurant")
            scope.restaurant_id = restaurant_id
            return scope

        role: MemberRole | None = await scope.session.scalar(
            select(RestaurantMember.role).where(
                RestaurantMember.restaurant_id == restaurant_id,
                RestaurantMember.user_id == p.user_id,
            )
        )
        if role is None:
            if not p.is_platform_admin:
                raise Forbidden("not a member of this restaurant")
        elif not role.can_act_as(min_role):
            raise Forbidden(f"requires at least '{min_role.value}' role")

        # Elevate: pin the tenant GUC for the rest of this transaction.
        await scope.session.execute(
            text("SELECT set_config('app.restaurant_id', :v, true)"),
            {"v": str(restaurant_id)},
        )
        scope.restaurant_id = restaurant_id
        scope.role = role
        return scope

    return dependency
