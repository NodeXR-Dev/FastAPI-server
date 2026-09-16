"""Align AGENT_GUIDE enums with the client event spec.

Revision ID: 20260916_04
Revises: 20260916_03
Create Date: 2026-09-16
"""

from alembic import op


revision = "20260916_04"
down_revision = "20260916_03"
branch_labels = None
depends_on = None


# 기존 값 → 스펙 이름. RENAME이라 기존 행은 그대로 따라온다.
ALERT_TYPE_RENAMES = [
    ("DECISION_VIOLATION", "DECISION_CONFLICT"),
    ("LONG_RUNNING_CONFLICT", "LONG_UNRESOLVED_CONFLICT"),
    ("TOPIC_DRIFT_WITH_OPEN_CONFLICT", "TOPIC_SHIFT_WITH_UNRESOLVED_CONFLICT"),
    ("CONFLICT_ARGUMENT_RECALL", "CONFLICT_RATIONALE_RECALL"),
    ("PART_DECISION_CONFLICT", "PART_GLOBAL_DECISION_CONFLICT"),
]


def upgrade() -> None:
    for old, new in ALERT_TYPE_RENAMES:
        op.execute(f"ALTER TYPE alert_type RENAME VALUE '{old}' TO '{new}'")
    op.execute(
        "ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'SIMILAR_CONFLICT_REPEATED'"
    )
    op.execute("ALTER TYPE design_fact_type ADD VALUE IF NOT EXISTS 'ISSUE'")
    op.execute("ALTER TYPE design_fact_status ADD VALUE IF NOT EXISTS 'RESOLVED'")
    op.execute("ALTER TYPE memory_status ADD VALUE IF NOT EXISTS 'SUPERSEDED'")


def downgrade() -> None:
    for old, new in ALERT_TYPE_RENAMES:
        op.execute(f"ALTER TYPE alert_type RENAME VALUE '{new}' TO '{old}'")
    # PostgreSQL enum 값은 타입을 재생성하지 않으면 제거할 수 없다.
    # 추가된 값이 남아 있어도 이전 애플리케이션 버전과 호환된다.
