"""Add utterance_annotations for structure-based Agent gating.

Revision ID: 20260916_03
Revises: 20260916_02
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260916_03"
down_revision = "20260916_02"
branch_labels = None
depends_on = None


DIALOGUE_MOVE = (
    "PROPOSE",
    "DECIDE",
    "ASK",
    "AGREE",
    "DISAGREE",
    "INFORM",
    "OTHER",
)
STANCE = ("FOR", "AGAINST", "NEUTRAL")


def upgrade() -> None:
    dialogue_move = postgresql.ENUM(*DIALOGUE_MOVE, name="dialogue_move")
    stance = postgresql.ENUM(*STANCE, name="stance")
    dialogue_move.create(op.get_bind(), checkfirst=True)
    stance.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "utterance_annotations",
        sa.Column(
            "utterance_annotation_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "utterance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("utterances.utterance_id"),
            nullable=False,
        ),
        sa.Column(
            "dialogue_move",
            postgresql.ENUM(*DIALOGUE_MOVE, name="dialogue_move", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "stance",
            postgresql.ENUM(*STANCE, name="stance", create_type=False),
            nullable=False,
            server_default="NEUTRAL",
        ),
        sa.Column(
            "target_fact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("design_facts.design_fact_id"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "utterance_id",
            "model_version",
            name="uq_utterance_annotations_utterance_model",
        ),
    )
    op.create_index(
        "ix_utterance_annotations_utterance_id",
        "utterance_annotations",
        ["utterance_id"],
    )
    op.create_index(
        "ix_utterance_annotations_dialogue_move",
        "utterance_annotations",
        ["dialogue_move"],
    )
    op.create_index(
        "ix_utterance_annotations_target_fact_id",
        "utterance_annotations",
        ["target_fact_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_utterance_annotations_target_fact_id",
        table_name="utterance_annotations",
    )
    op.drop_index(
        "ix_utterance_annotations_dialogue_move",
        table_name="utterance_annotations",
    )
    op.drop_index(
        "ix_utterance_annotations_utterance_id",
        table_name="utterance_annotations",
    )
    op.drop_table("utterance_annotations")
    postgresql.ENUM(name="stance").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="dialogue_move").drop(op.get_bind(), checkfirst=True)
