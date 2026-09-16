"""Add HNSW vector indexes for Agent retrieval paths.

Revision ID: 20260916_01
Revises: 20260809_01
Create Date: 2026-09-16
"""

from alembic import op


revision = "20260916_01"
down_revision = "20260809_01"
branch_labels = None
depends_on = None


# 세 컬럼 모두 cosine_distance(<=>)로만 조회되므로 vector_cosine_ops를 사용한다.
HNSW_INDEXES = (
    ("ix_design_facts_embedding_hnsw", "design_facts", "embedding"),
    ("ix_semantic_memories_embedding_hnsw", "semantic_memories", "embedding"),
    ("ix_topics_centroid_embedding_hnsw", "topics", "centroid_embedding"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for index_name, table_name, column_name in HNSW_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table_name} USING hnsw ({column_name} vector_cosine_ops)"
        )


def downgrade() -> None:
    for index_name, _table_name, _column_name in HNSW_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
