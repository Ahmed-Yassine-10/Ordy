"""Async engine, session factory, and the tenant-context (RLS) mechanism.

The isolation invariant (doc 06 §4, doc 08 §3): the app connects as a role WITHOUT
BYPASSRLS. Every unit of work sets transaction-local GUCs via ``set_config(..., true)``
(equivalent to ``SET LOCAL``), which are scoped to the surrounding transaction and are
therefore safe under PgBouncer transaction pooling:

    app.user_id           — the authenticated user (enables "my memberships" policies)
    app.restaurant_id     — the active tenant (enables tenant-table policies)
    app.is_platform_admin — 'on' for the audited admin path, else 'off'

Nothing loads tenant data into memory before the matching GUC is set.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Who is acting, and on which tenant, for one unit of work."""

    user_id: uuid.UUID | None = None
    restaurant_id: uuid.UUID | None = None
    is_platform_admin: bool = False


async def apply_tenant_context(session: AsyncSession, ctx: TenantContext) -> None:
    """Set transaction-local GUCs that the RLS policies read. Call inside a txn."""
    await session.execute(
        text("SELECT set_config('app.user_id', :v, true)"),
        {"v": str(ctx.user_id) if ctx.user_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.restaurant_id', :v, true)"),
        {"v": str(ctx.restaurant_id) if ctx.restaurant_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.is_platform_admin', :v, true)"),
        {"v": "on" if ctx.is_platform_admin else "off"},
    )


class Database:
    """Owns the engine + session factory. One instance per process."""

    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 10) -> None:
        self._engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=5,
            pool_pre_ping=True,
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False, autoflush=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self, ctx: TenantContext | None = None) -> AsyncIterator[AsyncSession]:
        """A session wrapped in one transaction, with tenant GUCs applied up front.

        Commits on success, rolls back on error. Because the GUCs are SET LOCAL,
        they vanish with the transaction — no context can leak to a pooled peer.
        """
        async with self._sessionmaker() as session:
            async with session.begin():
                if ctx is not None:
                    await apply_tenant_context(session, ctx)
                yield session

    async def dispose(self) -> None:
        await self._engine.dispose()
