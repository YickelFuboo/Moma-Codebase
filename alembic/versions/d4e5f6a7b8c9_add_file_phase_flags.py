"""add is_embedded / is_symboled; retire status=embedded

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repo_file_analysis_state",
        sa.Column(
            "is_embedded",
            sa.Boolean(),
            nullable=False,
            server_default="0",
            comment="行块 embedding 已入库（可检索）",
        ),
    )
    op.add_column(
        "repo_file_analysis_state",
        sa.Column(
            "is_symboled",
            sa.Boolean(),
            nullable=False,
            server_default="0",
            comment="符号摘要已补齐",
        ),
    )
    op.execute(
        """
        UPDATE repo_file_analysis_state
        SET
          is_embedded = CASE
            WHEN status IN ('embedded', 'completed') THEN 1
            ELSE 0
          END,
          is_symboled = CASE
            WHEN status = 'completed' THEN 1
            ELSE 0
          END,
          status = CASE
            WHEN status = 'embedded' THEN 'pending'
            ELSE status
          END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE repo_file_analysis_state
        SET status = CASE
          WHEN is_embedded = 1 AND is_symboled = 0 AND status IN ('pending', 'failed') THEN 'embedded'
          WHEN is_embedded = 1 AND is_symboled = 1 THEN 'completed'
          ELSE status
        END
        """
    )
    op.drop_column("repo_file_analysis_state", "is_symboled")
    op.drop_column("repo_file_analysis_state", "is_embedded")
