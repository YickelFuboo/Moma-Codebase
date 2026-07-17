from typing import Optional
import click
from app.cli.common import echo_json, get_repo_by_path, run_async
from app.repo_analysis.services.inspect_service import InspectService
from app.repo_mgmt.models.git_repo_mgmt import RepoKind


@click.group()
def inspect() -> None:
    """只读验收：切片 / Graph / Lib API（JSON，可导出）"""


def _emit(data: dict, export: Optional[str]) -> None:
    if export:
        path = InspectService.write_export(data, export)
        click.echo(f"已导出: {path}")
        click.echo(f"total={data.get('total')}")
    else:
        echo_json(data)


@inspect.command("chunks")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--target", default=None, help="相对子目录或文件；不填=全仓")
@click.option("--limit", default=InspectService.DEFAULT_LIMIT, show_default=True, help="返回条数上限，0=不限制")
@click.option("--full-content", is_flag=True, default=False, help="输出完整 content，默认仅 preview")
@click.option("--export", "export_path", default=None, help="导出到 JSON 文件")
def inspect_chunks(
    path: str,
    target: Optional[str],
    limit: int,
    full_content: bool,
    export_path: Optional[str],
) -> None:
    """查询切片（行块）数据"""

    async def _run() -> None:
        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind != RepoKind.CODE:
            raise click.ClickException(f"inspect chunks 仅支持 kind=code，当前 kind={kind}")
        data = await InspectService.inspect_chunks(
            repo.id,
            target=target,
            limit=limit,
            full_content=full_content,
        )
        data["path"] = path
        data["kind"] = kind
        _emit(data, export_path)

    run_async(_run)


@inspect.command("graph")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--target", default=None, help="相对子目录或文件；不填=全仓已分析文件")
@click.option("--limit", default=InspectService.DEFAULT_LIMIT, show_default=True, help="文件数上限，0=不限制")
@click.option("--export", "export_path", default=None, help="导出到 JSON 文件")
def inspect_graph(path: str, target: Optional[str], limit: int, export_path: Optional[str]) -> None:
    """查询 Graph 依赖关系数据"""

    async def _run() -> None:
        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind != RepoKind.CODE:
            raise click.ClickException(f"inspect graph 仅支持 kind=code，当前 kind={kind}")
        data = await InspectService.inspect_graph(repo.id, target=target, limit=limit)
        data["path"] = path
        data["kind"] = kind
        _emit(data, export_path)

    run_async(_run)


@inspect.command("apis")
@click.option("--path", required=True, help="已登记的本地 Lib 目录")
@click.option("--file", "file_path", default=None, help="相对文件路径；不填=全库接口")
@click.option("--limit", default=InspectService.DEFAULT_LIMIT, show_default=True, help="返回条数上限，0=不限制")
@click.option("--export", "export_path", default=None, help="导出到 JSON 文件")
def inspect_apis(path: str, file_path: Optional[str], limit: int, export_path: Optional[str]) -> None:
    """查询 Lib 公开接口数据"""

    async def _run() -> None:
        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind != RepoKind.LIB:
            raise click.ClickException(f"inspect apis 仅支持 kind=lib，当前 kind={kind}")
        data = await InspectService.inspect_apis(repo.id, file_path=file_path, limit=limit)
        data["path"] = path
        data["kind"] = kind
        _emit(data, export_path)

    run_async(_run)
