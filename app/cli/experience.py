import click
from typing import Optional
from app.cli.common import echo_json, get_repo_by_path, is_session_active, run_async
from app.repo_mgmt.models.git_repo_mgmt import RepoKind


@click.group(invoke_without_command=True)
@click.option("--path", default=None, help="已登记的本地代码仓目录（启动经验分析时必填）")
@click.option("--since", default=None, help="仅分析该日期之后的提交，如 2025-01-01")
@click.option("--limit", default=50, show_default=True, help="最多分析的提交条数")
@click.pass_context
def experience(ctx: click.Context, path: Optional[str], since: Optional[str], limit: int) -> None:
    """历史合入经验：experience --path 启动；子命令 status/clear。"""
    if ctx.invoked_subcommand is not None:
        return
    if not path:
        raise click.ClickException("启动经验分析请使用: experience --path <本地目录>")

    async def _start() -> None:
        from app.repo_analysis.services.experience_service import ExperienceService

        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind != RepoKind.CODE:
            raise click.ClickException(f"experience 仅支持 kind=code，当前 kind={kind}")
        result = await ExperienceService.start_analyze(repo.id, since=since, limit=limit)
        result.pop("repo_id", None)
        result["path"] = path
        result["kind"] = kind
        echo_json(result)

    run_async(_start, scheduler=True)
    if not is_session_active():
        click.echo("已登记经验分析任务。一次性模式下进程退出后后台任务会结束；长任务请使用交互模式: mcb")


@experience.command("analyze")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--since", default=None, help="仅分析该日期之后的提交")
@click.option("--limit", default=50, show_default=True, help="最多分析的提交条数")
def experience_analyze(path: str, since: Optional[str], limit: int) -> None:
    """启动历史合入经验分析（与 experience --path 等价）。"""

    async def _start() -> None:
        from app.repo_analysis.services.experience_service import ExperienceService

        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind != RepoKind.CODE:
            raise click.ClickException(f"experience 仅支持 kind=code，当前 kind={kind}")
        result = await ExperienceService.start_analyze(repo.id, since=since, limit=limit)
        result.pop("repo_id", None)
        result["path"] = path
        result["kind"] = kind
        echo_json(result)

    run_async(_start, scheduler=True)


@experience.command("status")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
def experience_status(path: str) -> None:
    """查看经验分析进度。"""

    async def _status() -> None:
        from app.repo_analysis.services.experience_service import ExperienceService

        repo = await get_repo_by_path(path)
        summary = await ExperienceService.get_status(repo.id)
        summary.pop("repo_id", None)
        summary["path"] = path
        echo_json(summary)

    run_async(_status)


@experience.command("clear")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.confirmation_option(prompt="确认清空该仓库的全部经验数据？")
def experience_clear(path: str) -> None:
    """清空已沉淀的经验数据。"""

    async def _clear() -> None:
        from app.repo_analysis.services.experience_service import ExperienceService

        repo = await get_repo_by_path(path)
        await ExperienceService.clear(repo.id)
        click.echo(f"已清空经验数据: {path}")

    run_async(_clear)
