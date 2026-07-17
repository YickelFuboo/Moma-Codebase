"""add session is_internal column

Revision ID: a1b2c3d4e5f6
Revises: 205e8f2ab379
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "205e8f2ab379"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column(
            "is_internal",
            sa.Boolean(),
            server_default="0",
            nullable=False,
            comment="内部派生 session，不展示在用户历史",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_sessions", "is_internal")
