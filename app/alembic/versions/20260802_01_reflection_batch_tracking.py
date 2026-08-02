"""Add durable Reflection Batch processing state.

Revision ID: 20260802_01
Revises:
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE design_fact_status ADD VALUE IF NOT EXISTS 'SUPERSEDED'"
    )
    op.add_column(
        "graph_events",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_graph_events_processed_room",
        "graph_events",
        ["processed_at", "room_id"],
        unique=False,
    )
    op.create_index(
        "ix_utterances_state_room",
        "utterances",
        ["state", "room_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_utterances_state_room", table_name="utterances")
    op.drop_index("ix_graph_events_processed_room", table_name="graph_events")
    op.drop_column("graph_events", "processed_at")
    # PostgreSQL enum values cannot be removed safely without rebuilding the type.
    # Keeping SUPERSEDED is backward compatible with older application versions.
