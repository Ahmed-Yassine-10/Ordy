"""automation: workflows + runs (+ RLS)

Revision ID: 0007_automation
Revises: 0006_orders
Create Date: 2026-07-24

Phase 8 (roadmap doc 10). Browser workflows are approved artifacts; runs recordper-step
results and an artifacts prefix. Both tenant-scoped under the usual FORCE'd RLS.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from ordy_core.db import Base

import ordy_core.models  # noqa: F401  — populate Base.metadata

revision: str = "0007_automation"
down_revision: str | None = "0006_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ["automation_workflows", "automation_runs"]


def _tenant_rls(table: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_all ON {table}
  USING (app_is_admin() OR restaurant_id = app_current_restaurant())
  WITH CHECK (app_is_admin() OR restaurant_id = app_current_restaurant());
"""


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    for table in _NEW_TENANT_TABLES:
        op.execute(_tenant_rls(table))


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP TYPE IF EXISTS workflowstatus")
