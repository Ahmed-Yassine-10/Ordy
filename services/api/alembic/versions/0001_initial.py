"""initial schema: identity, tenancy, menu + Row-Level Security

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-23

Phase 2 covers the identity/tenancy/menu core (roadmap doc 10). Tables are built
from the SQLAlchemy metadata, then the RLS layer (helper functions + per-table
policies) is applied on top. Later phases add orders, conversations, knowledge, etc.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from ordy_core.db import Base

import ordy_core.models  # noqa: F401  — populate Base.metadata

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tenant tables whose policy is the simple "matches the active tenant" rule.
_SIMPLE_TENANT_TABLES = [
    "api_keys",
    "menus",
    "menu_categories",
    "products",
    "product_variants",
    "modifier_groups",
    "modifiers",
]

_RLS_HELPERS = """
-- GUC accessors. current_setting(..., true) returns NULL when unset → deny by default.
CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid
  LANGUAGE sql STABLE AS
  $fn$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $fn$;

CREATE OR REPLACE FUNCTION app_current_restaurant() RETURNS uuid
  LANGUAGE sql STABLE AS
  $fn$ SELECT nullif(current_setting('app.restaurant_id', true), '')::uuid $fn$;

CREATE OR REPLACE FUNCTION app_is_admin() RETURNS boolean
  LANGUAGE sql STABLE AS
  $fn$ SELECT coalesce(current_setting('app.is_platform_admin', true), 'off') = 'on' $fn$;

-- SECURITY DEFINER (owner = ordy_migrator, BYPASSRLS) so the membership check does
-- not recurse into restaurant_members' own RLS policy.
CREATE OR REPLACE FUNCTION app_is_member(rid uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
  $fn$ SELECT EXISTS (
         SELECT 1 FROM restaurant_members m
         WHERE m.restaurant_id = rid AND m.user_id = app_current_user()
       ) $fn$;

-- Auth-time API-key lookup runs before any tenant context exists → bypass RLS.
CREATE OR REPLACE FUNCTION app_api_key_candidates(p text) RETURNS SETOF api_keys
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
  $fn$ SELECT * FROM api_keys WHERE key_prefix = p AND revoked_at IS NULL $fn$;

GRANT EXECUTE ON FUNCTION
  app_current_user(), app_current_restaurant(), app_is_admin(),
  app_is_member(uuid), app_api_key_candidates(text)
  TO ordy_app;
"""

_RLS_RESTAURANTS = """
ALTER TABLE restaurants ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurants FORCE ROW LEVEL SECURITY;
CREATE POLICY restaurants_select ON restaurants FOR SELECT
  USING (app_is_admin() OR id = app_current_restaurant() OR app_is_member(id));
CREATE POLICY restaurants_insert ON restaurants FOR INSERT
  WITH CHECK (app_current_user() IS NOT NULL OR app_is_admin());
CREATE POLICY restaurants_update ON restaurants FOR UPDATE
  USING (app_is_admin() OR id = app_current_restaurant() OR app_is_member(id))
  WITH CHECK (app_is_admin() OR id = app_current_restaurant() OR app_is_member(id));
CREATE POLICY restaurants_delete ON restaurants FOR DELETE
  USING (app_is_admin() OR app_is_member(id));

ALTER TABLE restaurant_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE restaurant_members FORCE ROW LEVEL SECURITY;
CREATE POLICY members_select ON restaurant_members FOR SELECT
  USING (app_is_admin() OR user_id = app_current_user() OR restaurant_id = app_current_restaurant());
CREATE POLICY members_insert ON restaurant_members FOR INSERT
  WITH CHECK (app_is_admin() OR user_id = app_current_user() OR restaurant_id = app_current_restaurant());
CREATE POLICY members_update ON restaurant_members FOR UPDATE
  USING (app_is_admin() OR restaurant_id = app_current_restaurant())
  WITH CHECK (app_is_admin() OR restaurant_id = app_current_restaurant());
CREATE POLICY members_delete ON restaurant_members FOR DELETE
  USING (app_is_admin() OR restaurant_id = app_current_restaurant());
"""


def _simple_tenant_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_all ON {table}
  USING (app_is_admin() OR restaurant_id = app_current_restaurant())
  WITH CHECK (app_is_admin() OR restaurant_id = app_current_restaurant());
"""


def upgrade() -> None:
    bind = op.get_bind()
    # Extensions are created by initdb, but keep the migration self-sufficient.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Build all tables + enum types from the ORM metadata.
    Base.metadata.create_all(bind=bind)

    # Layer Row-Level Security on top.
    op.execute(_RLS_HELPERS)
    op.execute(_RLS_RESTAURANTS)
    for table in _SIMPLE_TENANT_TABLES:
        op.execute(_simple_tenant_rls(table))


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP FUNCTION IF EXISTS app_api_key_candidates(text)")
    op.execute("DROP FUNCTION IF EXISTS app_is_member(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_is_admin()")
    op.execute("DROP FUNCTION IF EXISTS app_current_restaurant()")
    op.execute("DROP FUNCTION IF EXISTS app_current_user()")
    Base.metadata.drop_all(bind=bind)
