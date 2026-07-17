import click
from app.cli.common import echo_json, get_repo_by_path, run_async
from app.repo_analysis.services.search_service import SearchService
from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
from app.repo_mgmt.models.git_repo_mgmt import RepoKind


def _assert_kind_code(repo) -> None:
    kind = getattr(repo, "kind", None) or RepoKind.CODE
    if kind != RepoKind.CODE:
        raise click.ClickException(f"该查询仅支持 kind=code，当前 kind={kind}")


def _assert_kind_lib(repo) -> None:
    kind = getattr(repo, "kind", None) or RepoKind.CODE
    if kind != RepoKind.LIB:
        raise click.ClickException(f"search api 仅支持 kind=lib，当前 kind={kind}")


@click.group()
def search() -> None:
    """代码检索与图谱查询（支持一次性与交互模式）"""


@search.command("resolve")
@click.option("--path", required=True, help="已登记的本地 Repo/Lib 目录")
@click.option("--query", required=True, help="自然语言描述或代码片段")
@click.option(
    "--intent",
    default="auto",
    show_default=True,
    help="auto|similar|related|locate|pattern|experience|api|graph",
)
@click.option("--top-k", default=10, show_default=True, help="融合结果条数")
def search_resolve(path: str, query: str, intent: str, top_k: int) -> None:
    """统一检索编排：按规则自动选择通道（Agent 主入口）。"""

    async def _resolve() -> None:
        from app.repo_analysis.services.search_resolve import SearchResolveService

        repo = await get_repo_by_path(path)
        try:
            result = await SearchResolveService.resolve(
                repo_id=repo.id,
                query=query,
                top_k=top_k,
                intent=intent,
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e
        result.pop("repo_id", None)
        result["path"] = path
        result["kind"] = getattr(repo, "kind", None) or RepoKind.CODE
        echo_json(result)

    run_async(_resolve)


@search.command("similar")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--code", required=True, help="待检索的代码片段")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
def search_similar(path: str, code: str, top_k: int) -> None:
    """相似代码片段检索（行块向量；仅 kind=code）"""

    async def _similar() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
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
    """相关代码检索：符号 exact/摘要 + CodeGraph（仅 kind=code）"""

    async def _related() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        result = await SearchService.search_related_files(
            repo_id=repo.id,
            keywords=keyword_list,
            top_k=top_k,
        )
        result["path"] = path
        echo_json(result)

    run_async(_related)


@search.command("chunks")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--query", required=True, help="查询文本（语义检索行块）")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
def search_chunks(path: str, query: str, top_k: int) -> None:
    """仅查询行块向量（人工调试；Agent 优先用 similar）"""

    async def _chunks() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
        result = await SearchService.search_chunks(repo_id=repo.id, query=query, top_k=top_k)
        result["path"] = path
        echo_json(result)

    run_async(_chunks)


@search.command("symbols")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--query", required=True, help="查询文本（语义检索符号摘要）")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
def search_symbols(path: str, query: str, top_k: int) -> None:
    """仅查询符号摘要向量（人工调试；Agent 优先用 related）"""

    async def _symbols() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
        result = await SearchService.search_symbols(repo_id=repo.id, query=query, top_k=top_k)
        result["path"] = path
        echo_json(result)

    run_async(_symbols)


@search.command("api")
@click.option("--path", required=True, help="已登记的本地 Lib 目录")
@click.option("--query", required=True, help="需求/接口描述")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
def search_api(path: str, query: str, top_k: int) -> None:
    """按需求检索 Lib 公开接口摘要（仅 kind=lib）"""

    async def _api() -> None:
        from app.lib_analysis.services.search_service import LibSearchService

        repo = await get_repo_by_path(path)
        _assert_kind_lib(repo)
        result = await LibSearchService.search_apis(
            repo_id=repo.id,
            query=query,
            top_k=top_k,
        )
        result["path"] = path
        echo_json(result)

    run_async(_api)


@search.command("pattern")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--query", required=True, help="需求/问题描述")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
def search_pattern(path: str, query: str, top_k: int) -> None:
    """按需求检索历史开发经验模式（独立经验接口；仅 kind=code）"""

    async def _pattern() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
        result = await SearchService.search_patterns(
            repo_id=repo.id,
            query=query,
            top_k=top_k,
        )
        result["path"] = path
        echo_json(result)

    run_async(_pattern)


@search.command("dependents")
@click.option("--path", required=True, help="已登记的本地代码仓目录")
@click.option("--file", "file_path", required=True, help="仓库内相对文件路径")
def search_dependents(path: str, file_path: str) -> None:
    """查询依赖指定文件的其他文件（仅 kind=code）"""

    async def _dependents() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
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
    """查询指定文件依赖的其他文件（仅 kind=code）"""

    async def _dependencies() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
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
    """查询调用指定符号的函数/方法（仅 kind=code）"""

    async def _callers() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
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
    """查询指定符号调用的函数/方法（仅 kind=code）"""

    async def _callees() -> None:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
        with CodeGraphGateway.create_search() as q:
            res = await q.query_callees_of_symbol(repo.id, symbol, limit=limit)
        if not res.result:
            raise click.ClickException(res.message or "查询失败")
        echo_json(res.content)

    run_async(_callees)
