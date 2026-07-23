"""ingestion: knowledge sources, runs, documents, capability maps (+ RLS)

Revision ID: 0002_ingestion
Revises: 0001_initial
Create Date: 2026-07-24

Phase 3 (roadmap doc 10). Adds the ingestion tables from the ORM metadata
(``create_all`` is checkfirst, so only the new tables are created) and layers the
same FORCE'd per-tenant RLS policy used by the menu tables.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from ordy_core.db import Base

import ordy_core.models  # noqa: F401  — populate Base.metadata

revision: str = "0002_ingestion"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = [
    "knowledge_sources",
    "ingestion_runs",
    "knowledge_documents",
    "capability_maps",
]


def _tenant_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_all ON {table}
  USING (app_is_admin() OR restaurant_id = app_current_restaurant())
  WITH CHECK (app_is_admin() OR restaurant_id = app_current_restaurant());
"""


def upgrade() -> None:
    bind = op.get_bind()
    # checkfirst=True → creates only the new tables + their enum types.
    Base.metadata.create_all(bind=bind)
    for table in _NEW_TENANT_TABLES:
        op.execute(_tenant_rls(table))


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for enum_type in ("sourcekind", "sourcestatus", "ingestiontrigger", "runstatus", "doctype", "docstatus", "mapstatus"):
        op.execute(f"DROP TYPE IF EXISTS {enum_type}")
