"""knowledge_chunks: pgvector embeddings + FTS + HNSW (+ RLS)

Revision ID: 0003_chunks
Revises: 0002_ingestion
Create Date: 2026-07-24

Phase 4 (roadmap doc 10). Adds the retrievable chunk table. The generated ``fts``
column, the GIN (lexical) index, and the HNSW (vector) index are created explicitly
after the table so we control operator classes.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from ordy_core.db import Base

import ordy_core.models  # noqa: F401  — populate Base.metadata

revision: str = "0003_chunks"
down_revision: str | None = "0002_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Creates knowledge_chunks (with the vector(1536) column). checkfirst skips the rest.
    Base.metadata.create_all(bind=bind)

    # Generated lexical column + hybrid-retrieval indexes.
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ADD COLUMN fts tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute("CREATE INDEX chunks_fts_idx ON knowledge_chunks USING gin (fts)")
    op.execute(
        "CREATE INDEX chunks_hnsw_idx ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # Same FORCE'd per-tenant policy as the other tenant tables (doc 06 §4).
    op.execute("ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_all ON knowledge_chunks "
        "USING (app_is_admin() OR restaurant_id = app_current_restaurant()) "
        "WITH CHECK (app_is_admin() OR restaurant_id = app_current_restaurant())"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")
