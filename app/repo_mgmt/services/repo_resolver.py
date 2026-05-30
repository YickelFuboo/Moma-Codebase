import os
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.repo_mgmt.models.git_repo_mgmt import GitRepository
from app.utils.common import normalize_path


class RepoResolver:
    """按 repo_id 或 repo_path 解析仓库。"""

    @staticmethod
    def normalize_repo_path(repo_path: str) -> str:
        return normalize_path(os.path.abspath(os.path.normpath(repo_path)))

    @staticmethod
    async def get_by_id(db: AsyncSession, repo_id: str) -> Optional[GitRepository]:
        result = await db.execute(select(GitRepository).where(GitRepository.id == repo_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_path(db: AsyncSession, repo_path: str) -> Optional[GitRepository]:
        normalized = RepoResolver.normalize_repo_path(repo_path)
        result = await db.execute(select(GitRepository))
        for repo in result.scalars().all():
            if not repo.local_path:
                continue
            repo_local = RepoResolver.normalize_repo_path(repo.local_path)
            if repo_local == normalized:
                return repo
        return None

    @staticmethod
    async def resolve(
        db: AsyncSession,
        repo_id: Optional[str] = None,
        repo_path: Optional[str] = None,
    ) -> Optional[GitRepository]:
        if repo_id:
            return await RepoResolver.get_by_id(db, repo_id)
        if repo_path:
            return await RepoResolver.get_by_path(db, repo_path)
        return None
