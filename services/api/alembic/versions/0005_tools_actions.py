"""tools: tool_definitions (global, seeded), restaurant_tools, action_executions (+ RLS)

Revision ID: 0005_tools
Revises: 0004_conversations
Create Date: 2026-07-24

Phase 6 (roadmap doc 10). The platform catalog is seeded FROM CODE (ordy_tools.catalog)
so the DB can never contain a tool the code doesn't implement. Tenant enablement and the
action audit are tenant-scoped under the usual FORCE'd RLS.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

from alembic import op
from ordy_core.db import Base
from ordy_tools.catalog import PLATFORM_TOOLS
from sqlalchemy import text

import ordy_core.models  # noqa: F401  — populate Base.metadata

revision: str = "0005_tools"
down_revision: str | None = "0004_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ["restaurant_tools", "action_executions"]


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
    Base.metadata.create_all(bind=bind)

    for table in _NEW_TENANT_TABLES:
        op.execute(_tenant_rls(table))

    # tool_definitions is global (readable by every tenant, writable only by migrations).
    insert = text(
        """
        INSERT INTO tool_definitions
            (id, key, version, title, description, risk, requires_confirmation, idempotent,
             input_schema, output_schema, validators, compensation, is_active, created_at, updated_at)
        VALUES
            (:id, :key, :version, :title, :description, :risk, :requires_confirmation, :idempotent,
             CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb), :validators,
             CAST(:compensation AS jsonb), true, now(), now())
        ON CONFLICT (key, version) DO NOTHING
        """
    )
    for spec in PLATFORM_TOOLS.values():
        bind.execute(
            insert,
            {
                "id": str(uuid.uuid4()),
                "key": spec.key,
                "version": spec.version,
                "title": spec.title,
                "description": spec.description,
                "risk": spec.risk.value,
                "requires_confirmation": spec.requires_confirmation,
                "idempotent": spec.idempotent,
                "input_schema": json.dumps(spec.input_schema),
                "output_schema": json.dumps(spec.output_schema),
                "validators": list(spec.validators),
                "compensation": json.dumps(spec.compensation) if spec.compensation else None,
            },
        )


def downgrade() -> None:
    for table in [*reversed(_NEW_TENANT_TABLES), "tool_definitions"]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP TYPE IF EXISTS actionstatus")
