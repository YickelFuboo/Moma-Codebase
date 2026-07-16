import click
from app.cli.common import echo_json, get_repo_by_path, run_async
from app.repo_analysis.services.search_service import SearchService
from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway


@click.group()
def search() -> None:
    """代码检索与图谱查询（支持一次性与交互模式）"""


@search.command("similar")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--code", required=True, help="待检索的代码片段")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
def search_similar(path: str, code: str, top_k: int) -> None:
    """相似代码检索"""

    async def _similar() -> None:
        repo = await get_repo_by_path(path)
        result = await SearchService.search_similar_code(
            repo_id=repo.id,
            code_text=code,
            top_k=top_k,
        )
        echo_json(result)

    run_async(_similar)


@search.command("related")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--keywords", required=True, help="检索关键词，逗号分隔")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
def search_related(path: str, keywords: str, top_k: int) -> None:
    """相关文件检索"""

    async def _related() -> None:
        repo = await get_repo_by_path(path)
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        result = await SearchService.search_related_files(
            repo_id=repo.id,
            keywords=keyword_list,
            top_k=top_k,
        )
        echo_json(result)

    run_async(_related)


@search.command("dependents")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--file", "file_path", required=True, help="仓库内相对文件路径")
def search_dependents(path: str, file_path: str) -> None:
    """查询依赖指定文件的其他文件"""

    async def _dependents() -> None:
        repo = await get_repo_by_path(path)
        with CodeGraphGateway.create_search() as q:
            res = await q.query_dependents_of_file(repo.id, file_path)
        if not res.result:
            raise click.ClickException(res.message or "查询失败")
        echo_json(res.content)

    run_async(_dependents)


@search.command("dependencies")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--file", "file_path", required=True, help="仓库内相对文件路径")
def search_dependencies(path: str, file_path: str) -> None:
    """查询指定文件依赖的其他文件"""

    async def _dependencies() -> None:
        repo = await get_repo_by_path(path)
        with CodeGraphGateway.create_search() as q:
            res = await q.query_dependented_of_file(repo.id, file_path)
        if not res.result:
            raise click.ClickException(res.message or "查询失败")
        echo_json(res.content)

    run_async(_dependencies)


@search.command("callers")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--symbol", required=True, help="符号名（函数/方法/类）")
@click.option("--limit", default=20, show_default=True, help="返回条数上限")
def search_callers(path: str, symbol: str, limit: int) -> None:
    """查询调用指定符号的函数/方法"""

    async def _callers() -> None:
        repo = await get_repo_by_path(path)
        with CodeGraphGateway.create_search() as q:
            res = await q.query_callers_of_symbol(repo.id, symbol, limit=limit)
        if not res.result:
            raise click.ClickException(res.message or "查询失败")
        echo_json(res.content)

    run_async(_callers)


@search.command("callees")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--symbol", required=True, help="符号名（函数/方法/类）")
@click.option("--limit", default=20, show_default=True, help="返回条数上限")
def search_callees(path: str, symbol: str, limit: int) -> None:
    """查询指定符号调用的函数/方法"""

    async def _callees() -> None:
        repo = await get_repo_by_path(path)
        with CodeGraphGateway.create_search() as q:
            res = await q.query_callees_of_symbol(repo.id, symbol, limit=limit)
        if not res.result:
            raise click.ClickException(res.message or "查询失败")
        echo_json(res.content)

    run_async(_callees)
