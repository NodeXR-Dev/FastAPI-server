"""Add SKIP state for Noise Filter classified utterances.

Revision ID: 20260916_02
Revises: 20260916_01
Create Date: 2026-09-16
"""

from alembic import op


revision = "20260916_02"
down_revision = "20260916_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE utterance_state ADD VALUE IF NOT EXISTS 'SKIP'")


def downgrade() -> None:
    # PostgreSQL enum 값은 타입을 재생성하지 않으면 제거할 수 없다.
    # SKIP이 남아 있어도 이전 애플리케이션 버전과 호환된다.
    pass
