"""Add soft deletion support to sub graphs.

Revision ID: 20260802_02
Revises: 20260802_01
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_02"
down_revision = "20260802_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sub_graphs",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sub_graphs_room_deleted",
        "sub_graphs",
        ["room_id", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sub_graphs_room_deleted", table_name="sub_graphs")
    op.drop_column("sub_graphs", "deleted_at")
