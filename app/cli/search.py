import click
from app.cli.common import get_repo_by_path, resolve_search_repos, run_async
from app.cli.schemes import ResponseScheme
from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
from app.repo_analysis.services.multi_path_search import MultiPathSearchService
from app.repo_analysis.services.search_service import SearchService
from app.repo_analysis.services.search_snippet import SearchSnippetAttacher
from app.repo_mgmt.models.git_repo_mgmt import RepoKind
from app.repo_mgmt.services.repo_resolver import RepoResolver


_PATH_HELP = (
    "已登记仓路径，或上级目录（前缀匹配展开子仓）；"
    "可重复 --path 做并集"
)
_TIMEOUT_HELP = "查询超时毫秒；0 表示不限制"


def _assert_kind_code(repo) -> None:
    kind = getattr(repo, "kind", None) or RepoKind.CODE
    if kind != RepoKind.CODE:
        raise click.ClickException(f"该查询仅支持 kind=code，当前 kind={kind}")


def _assert_kind_lib(repo) -> None:
    kind = getattr(repo, "kind", None) or RepoKind.CODE
    if kind != RepoKind.LIB:
        raise click.ClickException(f"search api 仅支持 kind=lib，当前 kind={kind}")


def _path_option():
    return click.option(
        "--path",
        "paths",
        multiple=True,
        required=True,
        help=_PATH_HELP,
    )


def _timeout_option():
    return click.option(
        "--timeout-ms",
        default=0,
        show_default=True,
        help=_TIMEOUT_HELP,
    )


async def _expand_target_paths(
    paths: tuple[str, ...],
    *,
    kind: str | None = None,
) -> list[str]:
    repos = await resolve_search_repos(paths, kind=kind)
    return [RepoResolver.normalize_repo_path(r.local_path) for r in repos if r.local_path]


def _attach_snippet(payload: dict, enabled: bool) -> dict:
    return SearchSnippetAttacher.attach_to_payload(payload, enabled=enabled)


def _emit(
    coro_factory,
    *,
    timeout_ms: int = 0,
    profile: str = ResponseScheme.PROFILE_SEARCH,
    with_content: bool | None = None,
) -> None:
    ResponseScheme.run_and_echo(
        coro_factory,
        timeout_ms=timeout_ms,
        profile=profile,
        with_content=with_content,
        attach_snippet=_attach_snippet if with_content is not None else None,
        run_async=run_async,
    )


def _graph_file_items(paths: list, *, relation: str) -> list[dict]:
    items = []
    for raw in paths or []:
        fp = str(raw or "").replace("\\", "/").strip()
        if not fp:
            continue
        items.append(
            {
                "file_path": fp,
                "match_source": "codegraph",
                "graph_relation": relation,
                "score": 1.0,
            }
        )
    return items


@click.group()
def search() -> None:
    """代码检索与图谱查询（支持一次性与交互模式）"""


@search.command("resolve")
@_path_option()
@click.option("--query", required=True, help="自然语言描述或代码片段")
@click.option(
    "--intent",
    default="auto",
    show_default=True,
    help="auto|similar|related|locate|pattern|experience|api|graph",
)
@click.option("--top-k", default=10, show_default=True, help="融合结果条数")
@_timeout_option()
@click.option(
    "--with-content/--no-with-content",
    default=True,
    show_default=True,
    help="命中项附加本地源码 snippet，便于直接喂上下文",
)
def search_resolve(
    paths: tuple[str, ...],
    query: str,
    intent: str,
    top_k: int,
    timeout_ms: int,
    with_content: bool,
) -> None:
    """统一检索编排（主入口）。支持多 --path 与上级目录前缀展开。"""

    async def _resolve() -> dict:
        from app.repo_analysis.services.search_resolve import SearchResolveService

        targets = await _expand_target_paths(paths)

        async def _one(path: str):
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
            result["path"] = path
            result["kind"] = getattr(repo, "kind", None) or RepoKind.CODE
            return result

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=top_k,
                run_one=_one,
                query_fields={"query": query, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(
        _resolve,
        timeout_ms=timeout_ms,
        profile=ResponseScheme.PROFILE_RESOLVE,
        with_content=with_content,
    )


@search.command("similar")
@_path_option()
@click.option("--code", required=True, help="待检索的代码片段")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
@_timeout_option()
@click.option(
    "--with-content/--no-with-content",
    default=True,
    show_default=True,
    help="命中项附加本地源码 snippet",
)
def search_similar(
    paths: tuple[str, ...],
    code: str,
    top_k: int,
    timeout_ms: int,
    with_content: bool,
) -> None:
    """相似代码片段检索（行块向量；仅 kind=code）。"""

    async def _similar() -> dict:
        targets = await _expand_target_paths(paths, kind=RepoKind.CODE)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_code(repo)
            result = await SearchService.search_similar_code(
                repo_id=repo.id,
                code_text=code,
                top_k=top_k,
            )
            result["path"] = path
            result["kind"] = RepoKind.CODE
            result["repo_id"] = repo.id
            return result

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=top_k,
                run_one=_one,
                query_fields={"path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_similar, timeout_ms=timeout_ms, with_content=with_content)


@search.command("related")
@_path_option()
@click.option("--keywords", required=True, help="检索关键词，逗号分隔")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
@_timeout_option()
def search_related(
    paths: tuple[str, ...],
    keywords: str,
    top_k: int,
    timeout_ms: int,
) -> None:
    """相关代码检索：符号 exact/摘要 + CodeGraph（仅 kind=code）。"""

    async def _related() -> dict:
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        targets = await _expand_target_paths(paths, kind=RepoKind.CODE)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_code(repo)
            result = await SearchService.search_related_files(
                repo_id=repo.id,
                keywords=keyword_list,
                top_k=top_k,
            )
            result["path"] = path
            result["kind"] = RepoKind.CODE
            result["repo_id"] = repo.id
            return result

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=top_k,
                run_one=_one,
                query_fields={"keywords": keyword_list, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_related, timeout_ms=timeout_ms)


@search.command("chunks")
@_path_option()
@click.option("--query", required=True, help="查询文本（语义检索行块）")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
@_timeout_option()
def search_chunks(paths: tuple[str, ...], query: str, top_k: int, timeout_ms: int) -> None:
    """仅查询行块向量（人工调试；主路径优先用 similar）。"""

    async def _chunks() -> dict:
        targets = await _expand_target_paths(paths, kind=RepoKind.CODE)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_code(repo)
            result = await SearchService.search_chunks(repo_id=repo.id, query=query, top_k=top_k)
            result["path"] = path
            result["kind"] = RepoKind.CODE
            result["repo_id"] = repo.id
            return result

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=top_k,
                run_one=_one,
                query_fields={"query": query, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_chunks, timeout_ms=timeout_ms)


@search.command("symbols")
@_path_option()
@click.option("--query", required=True, help="查询文本（语义检索符号摘要）")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
@_timeout_option()
def search_symbols(paths: tuple[str, ...], query: str, top_k: int, timeout_ms: int) -> None:
    """仅查询符号摘要向量（人工调试；主路径优先用 related）。"""

    async def _symbols() -> dict:
        targets = await _expand_target_paths(paths, kind=RepoKind.CODE)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_code(repo)
            result = await SearchService.search_symbols(repo_id=repo.id, query=query, top_k=top_k)
            result["path"] = path
            result["kind"] = RepoKind.CODE
            result["repo_id"] = repo.id
            return result

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=top_k,
                run_one=_one,
                query_fields={"query": query, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_symbols, timeout_ms=timeout_ms)


@search.command("api")
@_path_option()
@click.option("--query", required=True, help="需求/接口描述")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
@_timeout_option()
def search_api(paths: tuple[str, ...], query: str, top_k: int, timeout_ms: int) -> None:
    """按需求检索 Lib 公开接口摘要（仅 kind=lib）。"""

    async def _api() -> dict:
        from app.lib_analysis.services.search_service import LibSearchService

        targets = await _expand_target_paths(paths, kind=RepoKind.LIB)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_lib(repo)
            result = await LibSearchService.search_apis(
                repo_id=repo.id,
                query=query,
                top_k=top_k,
            )
            result["path"] = path
            result["kind"] = RepoKind.LIB
            result["repo_id"] = repo.id
            return result

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=top_k,
                run_one=_one,
                query_fields={"query": query, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_api, timeout_ms=timeout_ms)


@search.command("pattern")
@_path_option()
@click.option("--query", required=True, help="需求/问题描述")
@click.option("--top-k", default=10, show_default=True, help="返回条数")
@_timeout_option()
def search_pattern(paths: tuple[str, ...], query: str, top_k: int, timeout_ms: int) -> None:
    """按需求检索历史开发经验模式（独立经验接口；仅 kind=code）。"""

    async def _pattern() -> dict:
        targets = await _expand_target_paths(paths, kind=RepoKind.CODE)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_code(repo)
            result = await SearchService.search_patterns(
                repo_id=repo.id,
                query=query,
                top_k=top_k,
            )
            result["path"] = path
            result["kind"] = RepoKind.CODE
            result["repo_id"] = repo.id
            return result

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=top_k,
                run_one=_one,
                query_fields={"query": query, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_pattern, timeout_ms=timeout_ms)


@search.command("dependents")
@click.option("--path", required=True, help="已登记的本地代码仓目录（须精确到单仓）")
@click.option("--file", "file_path", required=True, help="仓库内相对文件路径")
@_timeout_option()
def search_dependents(path: str, file_path: str, timeout_ms: int) -> None:
    """查询依赖指定文件的其他文件（仅 kind=code）"""

    async def _dependents() -> dict:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
        with CodeGraphGateway.create_search() as q:
            res = await q.query_dependents_of_file(repo.id, file_path)
        if not res.result:
            raise click.ClickException(res.message or "查询失败")
        content = dict(res.content or {})
        deps = list(content.get("dependents") or [])
        items = _graph_file_items(deps, relation="dependents")
        return {
            "path": RepoResolver.normalize_repo_path(path),
            "repo_id": repo.id,
            "kind": RepoKind.CODE,
            "file": file_path,
            "total": len(items),
            "items": items,
            "dependents": deps,
        }

    _emit(_dependents, timeout_ms=timeout_ms)


@search.command("dependencies")
@click.option("--path", required=True, help="已登记的本地代码仓目录（须精确到单仓）")
@click.option("--file", "file_path", required=True, help="仓库内相对文件路径")
@_timeout_option()
def search_dependencies(path: str, file_path: str, timeout_ms: int) -> None:
    """查询指定文件依赖的其他文件（仅 kind=code）"""

    async def _dependencies() -> dict:
        repo = await get_repo_by_path(path)
        _assert_kind_code(repo)
        with CodeGraphGateway.create_search() as q:
            res = await q.query_dependented_of_file(repo.id, file_path)
        if not res.result:
            raise click.ClickException(res.message or "查询失败")
        content = dict(res.content or {})
        deps = list(content.get("dependented") or content.get("dependencies") or [])
        items = _graph_file_items(deps, relation="dependencies")
        return {
            "path": RepoResolver.normalize_repo_path(path),
            "repo_id": repo.id,
            "kind": RepoKind.CODE,
            "file": file_path,
            "total": len(items),
            "items": items,
            "dependencies": deps,
        }

    _emit(_dependencies, timeout_ms=timeout_ms)


@search.command("callers")
@_path_option()
@click.option("--symbol", required=True, help="符号名（函数/方法/类）")
@click.option("--limit", default=20, show_default=True, help="返回条数上限")
@_timeout_option()
def search_callers(
    paths: tuple[str, ...],
    symbol: str,
    limit: int,
    timeout_ms: int,
) -> None:
    """查询调用指定符号的函数/方法（仅 kind=code）。"""

    async def _callers() -> dict:
        targets = await _expand_target_paths(paths, kind=RepoKind.CODE)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_code(repo)
            with CodeGraphGateway.create_search() as q:
                res = await q.query_callers_of_symbol(repo.id, symbol, limit=limit)
            if not res.result:
                raise click.ClickException(res.message or "查询失败")
            content = dict(res.content or {})
            items = []
            for hit in content.get("callers") or content.get("items") or []:
                if isinstance(hit, dict):
                    row = dict(hit)
                    row.setdefault("file_path", row.get("file") or row.get("path"))
                    row.setdefault("match_source", "codegraph")
                    row.setdefault("score", 1.0)
                    items.append(row)
            return {
                "path": path,
                "repo_id": repo.id,
                "kind": RepoKind.CODE,
                "total": len(items),
                "items": items,
            }

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=limit,
                run_one=_one,
                query_fields={"symbol": symbol, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_callers, timeout_ms=timeout_ms)


@search.command("callees")
@_path_option()
@click.option("--symbol", required=True, help="符号名（函数/方法/类）")
@click.option("--limit", default=20, show_default=True, help="返回条数上限")
@_timeout_option()
def search_callees(
    paths: tuple[str, ...],
    symbol: str,
    limit: int,
    timeout_ms: int,
) -> None:
    """查询指定符号调用的函数/方法（仅 kind=code）。"""

    async def _callees() -> dict:
        targets = await _expand_target_paths(paths, kind=RepoKind.CODE)

        async def _one(path: str):
            repo = await get_repo_by_path(path)
            _assert_kind_code(repo)
            with CodeGraphGateway.create_search() as q:
                res = await q.query_callees_of_symbol(repo.id, symbol, limit=limit)
            if not res.result:
                raise click.ClickException(res.message or "查询失败")
            content = dict(res.content or {})
            items = []
            for hit in content.get("callees") or content.get("items") or []:
                if isinstance(hit, dict):
                    row = dict(hit)
                    row.setdefault("file_path", row.get("file") or row.get("path"))
                    row.setdefault("match_source", "codegraph")
                    row.setdefault("score", 1.0)
                    items.append(row)
            return {
                "path": path,
                "repo_id": repo.id,
                "kind": RepoKind.CODE,
                "total": len(items),
                "items": items,
            }

        try:
            return await MultiPathSearchService.fanout(
                targets,
                top_k=limit,
                run_one=_one,
                query_fields={"symbol": symbol, "path_queries": list(paths)},
            )
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    _emit(_callees, timeout_ms=timeout_ms)
