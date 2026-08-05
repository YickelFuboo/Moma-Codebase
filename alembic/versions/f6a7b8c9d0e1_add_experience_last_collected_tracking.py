"""add last_collected tracking to repo_experience_tasks

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {str(r[1]) for r in rows}


def upgrade() -> None:
    cols = _columns("repo_experience_tasks")
    if "last_collected_commit_sha" not in cols:
        op.add_column(
            "repo_experience_tasks",
            sa.Column(
                "last_collected_commit_sha",
                sa.String(length=64),
                nullable=True,
                comment="最后一次收集到的 MR commit SHA（增量检测用）",
            ),
        )
    if "last_collected_committed_at" not in cols:
        op.add_column(
            "repo_experience_tasks",
            sa.Column(
                "last_collected_committed_at",
                sa.DateTime(),
                nullable=True,
                comment="最后一次收集到的 MR 提交时间（观测用）",
            ),
        )


def downgrade() -> None:
    cols = _columns("repo_experience_tasks")
    if "last_collected_committed_at" in cols:
        op.drop_column("repo_experience_tasks", "last_collected_committed_at")
    if "last_collected_commit_sha" in cols:
        op.drop_column("repo_experience_tasks", "last_collected_commit_sha")
