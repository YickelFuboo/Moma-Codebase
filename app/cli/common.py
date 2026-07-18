import asyncio
import json
import os
from typing import Any, Callable, Coroutine, List, Optional, Sequence, TypeVar
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


async def resolve_search_repos(
    paths: Sequence[str],
    user_id: str = DEFAULT_USER_ID,
    *,
    kind: Optional[str] = None,
) -> List[GitRepository]:
    """
    解析检索目标仓：支持
    1) 多个 --path 精确仓；
    2) 上级目录前缀，展开其下所有已登记仓；
    3) 二者组合（并集）；
    4) kind=code|lib 时只保留对应类型（resolve 可不传以同时覆盖）。
    """
    raw = [str(p).strip() for p in (paths or []) if str(p).strip()]
    if not raw:
        raise click.ClickException("至少指定一个 --path")
    async with get_db_session() as db:
        repos = await RepoResolver.expand_search_paths(
            db, raw, user_id=user_id, kind=kind
        )
        if not repos:
            shown = ", ".join(RepoResolver.normalize_repo_path(p) for p in raw)
            kind_hint = f"，kind={kind}" if kind else ""
            raise click.ClickException(
                f"未找到匹配的已登记仓库（支持精确 path 或上级目录前缀{kind_hint}）: {shown}"
            )
        out: List[GitRepository] = []
        for repo in repos:
            await db.refresh(repo)
            db.expunge(repo)
            out.append(repo)
        return out


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
