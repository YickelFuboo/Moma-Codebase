import click
from app.cli.common import (
    DEFAULT_USER_ID,
    default_repo_name,
    echo_json,
    get_repo_by_path,
    repo_public_view,
    run_async,
)
from app.infrastructure.database import get_db_session
from app.repo_mgmt.services.git_repo_service import GitRepositoryService
from app.repo_mgmt.services.repo_resolver import RepoResolver


@click.group()
def repo() -> None:
    """代码仓登记与管理（支持一次性与交互模式）"""


@repo.command("add")
@click.option("--path", required=True, type=click.Path(exists=True, file_okay=False), help="本地代码仓目录")
@click.option("--description", default="", show_default=True, help="仓库描述")
def repo_add(path: str, description: str) -> None:
    """登记本地代码仓（名称默认为目录名）"""

    async def _add() -> None:
        normalized = RepoResolver.normalize_repo_path(path)
        name = default_repo_name(normalized)
        async with get_db_session() as db:
            existing = await RepoResolver.get_by_path(db, normalized)
            if existing:
                raise click.ClickException(f"路径已登记: {normalized}")
            repo = await GitRepositoryService.create_repository_from_path(
                session=db,
                user_id=DEFAULT_USER_ID,
                name=name,
                description=description,
                local_repo_path=normalized,
                git_url="",
            )
            echo_json(repo_public_view(repo))

    run_async(_add)


@repo.command("list")
def repo_list() -> None:
    """列出已登记的代码仓"""

    async def _list() -> None:
        async with get_db_session() as db:
            repos, _total = await GitRepositoryService.get_repository_list(
                db, DEFAULT_USER_ID, page=1, page_size=1000
            )
            echo_json([repo_public_view(r) for r in repos])

    run_async(_list)


@repo.command("show")
@click.option("--path", required=True, type=click.Path(exists=True, file_okay=False), help="本地代码仓目录")
def repo_show(path: str) -> None:
    """查看已登记代码仓详情"""

    async def _show() -> None:
        repo = await get_repo_by_path(path)
        echo_json(repo_public_view(repo))

    run_async(_show)


@repo.command("delete")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.confirmation_option(prompt="确认删除该仓库登记及分析数据？")
def repo_delete(path: str) -> None:
    """删除代码仓登记（不删除磁盘上的源码目录）"""

    async def _delete() -> None:
        repo = await get_repo_by_path(path)
        async with get_db_session() as db:
            await GitRepositoryService.delete_repository(
                db,
                repository_id=repo.id,
                user_id=DEFAULT_USER_ID,
                delete_local=False,
            )
        click.echo(f"已删除: {RepoResolver.normalize_repo_path(path)}")

    run_async(_delete)
