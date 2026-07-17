"""add_mr_experience_tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repo_experience_tasks",
        sa.Column("repo_id", sa.String(length=36), nullable=False),
        sa.Column("job_status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["git_repositories.id"]),
        sa.PrimaryKeyConstraint("repo_id"),
    )
    op.create_index("idx_repo_experience_task_status", "repo_experience_tasks", ["job_status"])

    op.create_table(
        "mr_experience_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("repo_id", sa.String(length=36), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("commit_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("committed_at", sa.DateTime(), nullable=True),
        sa.Column("is_merge", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_files_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("steps_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["git_repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_id", "commit_sha", name="uq_mr_experience_repo_commit"),
    )
    op.create_index("idx_mr_experience_dispatch", "mr_experience_items", ["repo_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_mr_experience_dispatch", table_name="mr_experience_items")
    op.drop_table("mr_experience_items")
    op.drop_index("idx_repo_experience_task_status", table_name="repo_experience_tasks")
    op.drop_table("repo_experience_tasks")
