import asyncio
import json
import os
from typing import Any, Callable, Coroutine, Optional, TypeVar
import click
from app.infrastructure.database import get_db_session
from app.repo_mgmt.models.git_repo_mgmt import GitRepository
from app.repo_mgmt.services.repo_resolver import RepoResolver
from app.runtime import begin_long_session, end_long_session, ensure_scheduler, init_runtime, is_long_session, release_runtime

DEFAULT_USER_ID = "default"
T = TypeVar("T")
_session_loop: Optional[asyncio.AbstractEventLoop] = None


def begin_session(loop: asyncio.AbstractEventLoop) -> None:
    global _session_loop
    _session_loop = loop
    begin_long_session()


def end_session() -> None:
    global _session_loop
    _session_loop = None
    end_long_session()


def is_session_active() -> bool:
    return is_long_session()


def echo_json(data: Any) -> None:
    click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def run_async(
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    *,
    scheduler: bool = False,
) -> T:
    coro = _invoke(coro_factory(), scheduler=scheduler)
    if _session_loop is not None and is_long_session() and _session_loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, _session_loop).result()
    return asyncio.run(coro)


async def _invoke(coro: Coroutine[Any, Any, T], *, scheduler: bool) -> T:
    await init_runtime()
    if scheduler:
        await ensure_scheduler()
    try:
        return await coro
    finally:
        if not is_long_session():
            await release_runtime()


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
        "kind": getattr(repo, "kind", None) or "code",
        "description": repo.description or "",
        "git_provider": repo.git_provider,
        "repository_url": repo.repository_url or "",
        "branch": repo.branch,
        "created_at": repo.created_at,
        "updated_at": repo.updated_at,
    }


def default_repo_name(path: str) -> str:
    return os.path.basename(os.path.normpath(path)) or "repo"
