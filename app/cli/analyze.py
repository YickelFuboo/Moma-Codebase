import click
from app.cli.common import echo_json, get_repo_by_path, run_async
from app.code_analysis.services.repo_analysis_service import RepoAnalysisService


@click.group()
def analyze() -> None:
    """代码仓分析任务"""


@analyze.command("start")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
def analyze_start(path: str) -> None:
    """启动全仓扫描与分析"""

    async def _start() -> None:
        repo = await get_repo_by_path(path)
        result = await RepoAnalysisService.start_scan(repo_id=repo.id)
        result.pop("repo_id", None)
        result["path"] = path
        echo_json(result)

    run_async(_start)


@analyze.command("status")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
def analyze_status(path: str) -> None:
    """查看扫描与分析进度"""

    async def _status() -> None:
        repo = await get_repo_by_path(path)
        summary = await RepoAnalysisService.get_summary(repo.id)
        summary.pop("repo_id", None)
        summary["path"] = path
        echo_json(summary)

    run_async(_status)


@analyze.command("stop")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
def analyze_stop(path: str) -> None:
    """停止正在进行的扫描"""

    async def _stop() -> None:
        repo = await get_repo_by_path(path)
        result = await RepoAnalysisService.stop_scan(repo.id)
        result.pop("repo_id", None)
        result["path"] = path
        echo_json(result)

    run_async(_stop)


@analyze.command("clear")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.confirmation_option(prompt="确认清空该仓库的全部分析数据？")
def analyze_clear(path: str) -> None:
    """清空分析数据（向量、文件状态等）"""

    async def _clear() -> None:
        repo = await get_repo_by_path(path)
        await RepoAnalysisService.delete_repo_analysis_data(repo.id)
        click.echo(f"已清空分析数据: {path}")

    run_async(_clear)
