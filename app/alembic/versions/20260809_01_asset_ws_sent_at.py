"""Track successful 2D asset WebSocket delivery.

Revision ID: 20260809_01
Revises: 20260802_02
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_01"
down_revision = "20260802_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("ws_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_assets_room_type_ws_sent",
        "assets",
        ["room_id", "asset_type", "ws_sent_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_assets_room_type_ws_sent", table_name="assets")
    op.drop_column("assets", "ws_sent_at")
