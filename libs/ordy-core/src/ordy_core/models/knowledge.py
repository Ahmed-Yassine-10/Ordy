"""Knowledge & ingestion models (doc 06 §3.5).

Phase 3 scope: sources, runs, documents, capability maps. Chunks + embeddings
(``knowledge_chunks``, pgvector) arrive in Phase 4 with the RAG pipeline. All are
tenant-owned → RLS-protected.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

# Embedding dimensionality for the launch EMBEDDING tier. The concrete model + dim are
# recorded per-row in ``embedding_meta`` so an index migration is possible (ADR-008).
EMBEDDING_DIM = 1536

from ordy_core.db.base import Base, TenantMixin, TimestampMixin, pk
from ordy_core.enums import (
    DocStatus,
    DocType,
    IngestionTrigger,
    MapStatus,
    RunStatus,
    SourceKind,
    SourceStatus,
)


class KnowledgeSource(Base, TenantMixin, TimestampMixin):
    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[SourceKind] = mapped_column(nullable=False)
    # config holds url / repo etc. SECRETS ONLY AS VAULT REFS ("vault:sec_…"),
    # never plaintext credentials (doc 08 §4).
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schedule: Mapped[str | None] = mapped_column(Text)  # cron for re-sync
    status: Mapped[SourceStatus] = mapped_column(default=SourceStatus.ACTIVE, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column()


class IngestionRun(Base, TenantMixin, TimestampMixin):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[IngestionTrigger] = mapped_column(nullable=False)
    status: Mapped[RunStatus] = mapped_column(default=RunStatus.QUEUED, nullable=False)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[dict | None] = mapped_column(JSONB)
    artifacts_prefix: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


class KnowledgeDocument(Base, TenantMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = pk()
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("knowledge_sources.id", ondelete="SET NULL")
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    doc_type: Mapped[DocType] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # canonical markdown
    content_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DocStatus] = mapped_column(default=DocStatus.DRAFT, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # The extracted draft payload (menu items, hours, policies) prior to publish.
    draft: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column()


class KnowledgeChunk(Base, TenantMixin, TimestampMixin):
    """A retrievable slice of an APPROVED document (doc 06 §3.5).

    Rows exist only for approved knowledge — chunking + embedding happen in the same
    transaction as the approval flip, so a chunk is searchable iff approved
    (ADR-005/012). The ``fts`` generated column + HNSW index are created in migration
    0003 (kept off the ORM to avoid loading the tsvector on entity reads)."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    language: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class CapabilityMap(Base, TenantMixin, TimestampMixin):
    __tablename__ = "capability_maps"
    __table_args__ = (UniqueConstraint("restaurant_id", "version"),)

    id: Mapped[uuid.UUID] = pk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    map: Mapped[dict] = mapped_column(JSONB, nullable=False)  # doc 04 §3 format
    status: Mapped[MapStatus] = mapped_column(default=MapStatus.DRAFT, nullable=False)
    generated_from: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column()
