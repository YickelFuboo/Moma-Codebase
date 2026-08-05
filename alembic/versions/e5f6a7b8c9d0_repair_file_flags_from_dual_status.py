"""repair dual phase statuses into status + is_embedded/is_symboled

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    # PRAGMA: cid, name, type, notnull, dflt_value, pk
    return {str(r[1]) for r in rows}


def upgrade() -> None:
    cols = _columns("repo_file_analysis_state")
    if "embed_status" in cols:
        if "status" not in cols:
            op.add_column(
                "repo_file_analysis_state",
                sa.Column(
                    "status",
                    sa.String(length=32),
                    nullable=False,
                    server_default="pending",
                    comment="pending|running|completed|failed|skipped",
                ),
            )
        if "is_embedded" not in cols:
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
        if "is_symboled" not in cols:
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
                WHEN embed_status IN ('done', 'completed') THEN 1
                ELSE 0
              END,
              is_symboled = CASE
                WHEN symbol_status IN ('done', 'completed', 'skipped') THEN 1
                WHEN embed_status IN ('done', 'completed')
                     AND symbol_status IN ('done', 'completed', 'skipped') THEN 1
                ELSE 0
              END,
              status = CASE
                WHEN embed_status = 'running' OR symbol_status = 'running' THEN 'running'
                WHEN embed_status = 'failed' THEN 'failed'
                WHEN embed_status = 'skipped' THEN 'skipped'
                WHEN embed_status IN ('done', 'completed')
                     AND symbol_status IN ('done', 'completed', 'skipped') THEN 'completed'
                WHEN embed_status IN ('done', 'completed') THEN 'pending'
                ELSE 'pending'
              END
            """
        )
        # completed 强制双 true
        op.execute(
            """
            UPDATE repo_file_analysis_state
            SET is_embedded = 1, is_symboled = 1
            WHERE status = 'completed'
            """
        )
        op.drop_index("idx_repo_file_analysis_embed", table_name="repo_file_analysis_state")
        op.drop_index("idx_repo_file_analysis_symbol", table_name="repo_file_analysis_state")
        op.drop_column("repo_file_analysis_state", "symbol_status")
        op.drop_column("repo_file_analysis_state", "embed_status")
        op.create_index(
            "idx_repo_file_analysis_dispatch",
            "repo_file_analysis_state",
            ["repo_id", "status"],
            unique=False,
        )
        return

    # 正常路径：d4e5 已是 status + flags，无需再改
    cols = _columns("repo_file_analysis_state")
    if "is_embedded" in cols and "status" in cols:
        return
    raise RuntimeError(
        f"unexpected repo_file_analysis_state columns: {sorted(cols)}"
    )


def downgrade() -> None:
    cols = _columns("repo_file_analysis_state")
    if "embed_status" in cols:
        return
    op.add_column(
        "repo_file_analysis_state",
        sa.Column("embed_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "repo_file_analysis_state",
        sa.Column("symbol_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.execute(
        """
        UPDATE repo_file_analysis_state
        SET
          embed_status = CASE
            WHEN is_embedded = 1 THEN 'done'
            WHEN status = 'running' THEN 'running'
            WHEN status = 'failed' THEN 'failed'
            WHEN status = 'skipped' THEN 'skipped'
            ELSE 'pending'
          END,
          symbol_status = CASE
            WHEN is_symboled = 1 THEN 'done'
            WHEN is_embedded = 1 AND status = 'running' THEN 'running'
            WHEN is_embedded = 1 THEN 'pending'
            ELSE 'pending'
          END
        """
    )
    op.drop_index("idx_repo_file_analysis_dispatch", table_name="repo_file_analysis_state")
    op.drop_column("repo_file_analysis_state", "is_symboled")
    op.drop_column("repo_file_analysis_state", "is_embedded")
    op.drop_column("repo_file_analysis_state", "status")
    op.create_index(
        "idx_repo_file_analysis_embed",
        "repo_file_analysis_state",
        ["repo_id", "embed_status"],
        unique=False,
    )
    op.create_index(
        "idx_repo_file_analysis_symbol",
        "repo_file_analysis_state",
        ["repo_id", "symbol_status"],
        unique=False,
    )
