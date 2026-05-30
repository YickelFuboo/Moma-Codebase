import asyncio
import json
import os
from typing import Any, Callable, Coroutine, Optional, TypeVar
import click
from app.infrastructure.database import get_db_session
from app.repo_mgmt.models.git_repo_mgmt import GitRepository
from app.repo_mgmt.services.repo_resolver import RepoResolver
from app.runtime import shutdown, startup

DEFAULT_USER_ID = "default"
T = TypeVar("T")


def echo_json(data: Any) -> None:
    click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def run_async(coro_factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    return asyncio.run(_run_with_startup(coro_factory()))


async def _run_with_startup(coro: Coroutine[Any, Any, T]) -> T:
    await startup(start_scheduler=False)
    try:
        return await coro
    finally:
        await shutdown()


async def get_repo_by_path(path: str, user_id: str = DEFAULT_USER_ID) -> GitRepository:
    normalized = RepoResolver.normalize_repo_path(path)
    async with get_db_session() as db:
        repo = await RepoResolver.get_by_path(db, normalized)
        if not repo:
            raise click.ClickException(f"仓库未登记: {normalized}")
        if repo.user_id != user_id:
            raise click.ClickException(f"无权限访问仓库: {normalized}")
        await db.refresh(repo)
        db.expunge(repo)
        return repo


def repo_public_view(repo: GitRepository) -> dict[str, Any]:
    return {
        "path": RepoResolver.normalize_repo_path(repo.local_path) if repo.local_path else None,
        "name": repo.repository_name,
        "description": repo.description or "",
        "git_provider": repo.git_provider,
        "repository_url": repo.repository_url or "",
        "branch": repo.branch,
        "created_at": repo.created_at,
        "updated_at": repo.updated_at,
    }


def default_repo_name(path: str) -> str:
    return os.path.basename(os.path.normpath(path)) or "repo"
