"""Cross-tenant isolation suite (doc 06 §4, doc 08 §3, ADR-007).

Proves RLS blocks one tenant from reading/writing another's rows. This is a
permanent CI gate for every phase. Requires a running Postgres reachable via
DATABASE_URL with the migration already applied; skipped otherwise so the unit
suite stays runnable without infra.
"""

from __future__ import annotations

import os
import uuid

import pytest
from ordy_core.db import Database, TenantContext
from ordy_core.enums import MenuStatus
from ordy_core.models import Menu, Restaurant, User
from sqlalchemy import select

pytestmark = pytest.mark.asyncio

DB_URL = os.environ.get("DATABASE_URL")


@pytest.fixture
async def db() -> Database:
    if not DB_URL:
        pytest.skip("DATABASE_URL not set — integration test")
    database = Database(DB_URL)
    yield database
    await database.dispose()


async def _make_tenant(db: Database, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a restaurant + a published menu via the admin path. Returns (rid, menu_id)."""
    async with db.session(TenantContext(is_platform_admin=True)) as s:
        r = Restaurant(slug=slug, name=slug, currency="TND")
        s.add(r)
        await s.flush()
        m = Menu(restaurant_id=r.id, status=MenuStatus.PUBLISHED)
        s.add(m)
        await s.flush()
        return r.id, m.id


async def test_menu_is_invisible_across_tenants(db: Database) -> None:
    rid_a, menu_a = await _make_tenant(db, f"iso-a-{uuid.uuid4().hex[:8]}")
    rid_b, _ = await _make_tenant(db, f"iso-b-{uuid.uuid4().hex[:8]}")

    # Tenant B's context must NOT see tenant A's menu.
    async with db.session(TenantContext(restaurant_id=rid_b)) as s:
        found = await s.scalar(select(Menu).where(Menu.id == menu_a))
        assert found is None, "RLS leak: tenant B read tenant A's menu"

    # Tenant A's context sees its own menu.
    async with db.session(TenantContext(restaurant_id=rid_a)) as s:
        found = await s.scalar(select(Menu).where(Menu.id == menu_a))
        assert found is not None


async def test_cannot_write_into_another_tenant(db: Database) -> None:
    rid_a, _ = await _make_tenant(db, f"iso-c-{uuid.uuid4().hex[:8]}")
    rid_b, _ = await _make_tenant(db, f"iso-d-{uuid.uuid4().hex[:8]}")

    # Acting as tenant B, try to insert a menu tagged for tenant A → WITH CHECK denies it.
    from sqlalchemy.exc import DBAPIError, ProgrammingError

    with pytest.raises((DBAPIError, ProgrammingError)):
        async with db.session(TenantContext(restaurant_id=rid_b)) as s:
            s.add(Menu(restaurant_id=rid_a, status=MenuStatus.DRAFT))
            await s.flush()


async def test_identity_tables_have_no_tenant_leak_via_context(db: Database) -> None:
    # users is a global identity table (no tenant RLS); ensure basic access works
    # under a tenant context without error.
    async with db.session(TenantContext(restaurant_id=uuid.uuid4())) as s:
        # Should simply return nothing, not raise.
        await s.execute(select(User).limit(1))
