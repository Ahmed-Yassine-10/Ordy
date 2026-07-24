"""conversations: agent_configs, conversations, conversation_turns (+ RLS)

Revision ID: 0004_conversations
Revises: 0003_chunks
Create Date: 2026-07-24

Phase 5 (roadmap doc 10). Adds agent config + conversation persistence under the same
FORCE'd per-tenant RLS. conversation_turns is a plain table; monthly partitioning
(doc 06 §5) is a later production infra migration.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from ordy_core.db import Base

import ordy_core.models  # noqa: F401  — populate Base.metadata

revision: str = "0004_conversations"
down_revision: str | None = "0003_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ["agent_configs", "conversations", "conversation_turns"]


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
    for enum_type in ("channel", "conversationstatus", "turnrole"):
        op.execute(f"DROP TYPE IF EXISTS {enum_type}")
