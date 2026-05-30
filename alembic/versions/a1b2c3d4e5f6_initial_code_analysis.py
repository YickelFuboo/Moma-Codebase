"""initial_code_analysis

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'git_repositories',
        sa.Column('id', sa.String(), nullable=False, comment='ID'),
        sa.Column('user_id', sa.String(), nullable=False, comment='用户ID'),
        sa.Column('git_provider', sa.String(), nullable=False, comment='Git提供商'),
        sa.Column('repository_url', sa.String(), nullable=False, comment='仓库URL'),
        sa.Column('organization', sa.String(), nullable=False, comment='组织'),
        sa.Column('repository_name', sa.String(), nullable=False, comment='仓库名称'),
        sa.Column('branch', sa.String(), nullable=True, comment='分支'),
        sa.Column('description', sa.Text(), nullable=True, comment='仓库描述'),
        sa.Column('local_path', sa.String(), nullable=True, comment='本地路径'),
        sa.Column('is_cloned', sa.Boolean(), nullable=True, comment='是否已克隆'),
        sa.Column('last_sync_time', sa.DateTime(), nullable=True, comment='最后同步时间'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_git_repositories_id'), 'git_repositories', ['id'], unique=False)

    op.create_table(
        'git_authorities',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('access_token', sa.String(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_git_authorities_user_id'), 'git_authorities', ['user_id'], unique=False)
    op.create_index('idx_user_provider', 'git_authorities', ['user_id', 'provider'], unique=False)

    op.create_table(
        'repo_analysis_tasks',
        sa.Column('repo_id', sa.String(length=36), nullable=False, comment='代码仓ID'),
        sa.Column('scan_status', sa.String(length=32), nullable=False, comment='扫描任务状态'),
        sa.Column('last_error', sa.Text(), nullable=True, comment='最近错误'),
        sa.Column('last_scan_started_at', sa.DateTime(), nullable=True, comment='最近扫描开始时间'),
        sa.Column('last_scan_finished_at', sa.DateTime(), nullable=True, comment='最近扫描结束时间'),
        sa.Column('scan_heartbeat_at', sa.DateTime(), nullable=True, comment='扫描任务心跳时间'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['repo_id'], ['git_repositories.id'], ),
        sa.PrimaryKeyConstraint('repo_id')
    )
    op.create_index('idx_repo_analysis_task_scan_status', 'repo_analysis_tasks', ['scan_status'], unique=False)

    op.create_table(
        'repo_file_analysis_state',
        sa.Column('id', sa.String(length=36), nullable=False, comment='ID'),
        sa.Column('repo_id', sa.String(length=36), nullable=False, comment='代码仓ID'),
        sa.Column('file_path', sa.String(length=500), nullable=False, comment='相对路径'),
        sa.Column('status', sa.String(length=32), nullable=False, comment='状态'),
        sa.Column('last_error', sa.Text(), nullable=True, comment='最近错误'),
        sa.Column('last_started_at', sa.DateTime(), nullable=True, comment='最近开始分析时间'),
        sa.Column('last_finished_at', sa.DateTime(), nullable=True, comment='最近结束分析时间'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['repo_id'], ['git_repositories.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('repo_id', 'file_path', name='uq_repo_file')
    )
    op.create_index('idx_repo_file_analysis_dispatch', 'repo_file_analysis_state', ['repo_id', 'status'], unique=False)
    op.create_index('idx_repo_file_analysis_lookup', 'repo_file_analysis_state', ['repo_id', 'file_path'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_repo_file_analysis_lookup', table_name='repo_file_analysis_state')
    op.drop_index('idx_repo_file_analysis_dispatch', table_name='repo_file_analysis_state')
    op.drop_table('repo_file_analysis_state')
    op.drop_index('idx_repo_analysis_task_scan_status', table_name='repo_analysis_tasks')
    op.drop_table('repo_analysis_tasks')
    op.drop_index('idx_user_provider', table_name='git_authorities')
    op.drop_index(op.f('ix_git_authorities_user_id'), table_name='git_authorities')
    op.drop_table('git_authorities')
    op.drop_index(op.f('ix_git_repositories_id'), table_name='git_repositories')
    op.drop_table('git_repositories')
