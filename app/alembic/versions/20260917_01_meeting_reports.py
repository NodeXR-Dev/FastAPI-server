"""Add meeting_reports for the post-meeting decision report.

Revision ID: 20260917_01
Revises: 20260916_04
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260917_01"
down_revision = "20260916_04"
branch_labels = None
depends_on = None


MEETING_REPORT_STATUS = ("PENDING", "GENERATING", "COMPLETED", "FAILED")


def upgrade() -> None:
    meeting_report_status = postgresql.ENUM(
        *MEETING_REPORT_STATUS,
        name="meeting_report_status",
    )
    meeting_report_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "meeting_reports",
        sa.Column(
            "meeting_report_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.room_id"),
            nullable=False,
        ),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                *MEETING_REPORT_STATUS,
                name="meeting_report_status",
                create_type=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column(
            "final_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            nullable=True,
        ),
        sa.Column(
            "final_graph_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("graph_snapshots.graph_snapshot_id"),
            nullable=True,
        ),
        sa.Column("meeting_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meeting_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_data", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "room_id",
            "report_version",
            name="uq_meeting_reports_room_version",
        ),
    )
    op.create_index("ix_meeting_reports_room_id", "meeting_reports", ["room_id"])
    op.create_index("ix_meeting_reports_status", "meeting_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_meeting_reports_status", table_name="meeting_reports")
    op.drop_index("ix_meeting_reports_room_id", table_name="meeting_reports")
    op.drop_table("meeting_reports")
    postgresql.ENUM(name="meeting_report_status").drop(op.get_bind(), checkfirst=True)
