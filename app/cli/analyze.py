import click
from typing import Optional
from app.cli.common import echo_json, get_repo_by_path, is_session_active, run_async
from app.repo_analysis.services.analysis_service import AnalysisService
from app.repo_mgmt.models.git_repo_mgmt import RepoKind


@click.group(invoke_without_command=True)
@click.option("--path", default=None, help="已登记的本地代码仓目录（启动分析时必填）")
@click.pass_context
def analyze(ctx: click.Context, path: Optional[str]) -> None:
    """代码仓分析：analyze --path 启动；子命令 status/stop/clear。"""
    if ctx.invoked_subcommand is not None:
        return
    if not path:
        raise click.ClickException("启动分析请使用: analyze --path <本地目录>")

    async def _start() -> None:
        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind == RepoKind.LIB:
            from app.lib_analysis.services.analysis_service import LibAnalysisService

            result = await LibAnalysisService.start_scan(repo_id=repo.id)
        elif kind == RepoKind.CODE:
            result = await AnalysisService.start_scan(repo_id=repo.id)
        else:
            raise click.ClickException(f"不支持的 kind={kind}")
        result.pop("repo_id", None)
        result["path"] = path
        result["kind"] = kind
        echo_json(result)

    # 交互模式有长会话调度器；一次性命令也拉起调度器以便后台消费文件分析
    run_async(_start, scheduler=True)
    if not is_session_active():
        click.echo("已登记扫描任务。一次性模式下进程退出后后台任务会结束；长任务请使用交互模式: mcb")


@analyze.command("status")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
def analyze_status(path: str) -> None:
    """查看扫描与分析进度"""

    async def _status() -> None:
        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind == RepoKind.LIB:
            from app.lib_analysis.services.analysis_service import LibAnalysisService

            summary = await LibAnalysisService.get_summary(repo.id)
        else:
            summary = await AnalysisService.get_summary(repo.id)
        summary.pop("repo_id", None)
        summary["path"] = path
        summary["kind"] = kind
        echo_json(summary)

    run_async(_status)


@analyze.command("stop")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
def analyze_stop(path: str) -> None:
    """停止正在进行的扫描"""

    async def _stop() -> None:
        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind == RepoKind.LIB:
            from app.lib_analysis.services.analysis_service import LibAnalysisService

            result = await LibAnalysisService.stop_scan(repo.id)
        else:
            result = await AnalysisService.stop_scan(repo.id)
        result.pop("repo_id", None)
        result["path"] = path
        result["kind"] = kind
        echo_json(result)

    run_async(_stop)


@analyze.command("clear")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.confirmation_option(prompt="确认清空该仓库的全部分析数据？")
def analyze_clear(path: str) -> None:
    """清空分析数据（向量、文件状态等）"""

    async def _clear() -> None:
        repo = await get_repo_by_path(path)
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind == RepoKind.LIB:
            from app.lib_analysis.services.analysis_service import LibAnalysisService

            await LibAnalysisService.delete_repo_analysis_data(repo.id)
        else:
            await AnalysisService.delete_repo_analysis_data(repo.id)
        click.echo(f"已清空分析数据: {path}")

    run_async(_clear)
