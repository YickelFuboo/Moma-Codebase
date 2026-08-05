"""MCP 查询服务：复用 CLI/业务层，仅暴露查询能力。"""
from __future__ import annotations
from typing import Dict, List, Optional, Sequence
import click
from app.cli.common import DEFAULT_USER_ID, get_repo_by_path, resolve_search_repos, repo_public_view, run_async
from app.cli.doctor import DoctorService
from app.cli.schemes import ResponseScheme
from app.infrastructure.database import get_db_session
from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
from app.repo_analysis.services.multi_path_search import MultiPathSearchService
from app.repo_analysis.services.search_service import SearchService
from app.repo_analysis.services.search_snippet import SearchSnippetAttacher
from app.repo_mgmt.models.git_repo_mgmt import RepoKind
from app.repo_mgmt.services.git_repo_service import GitRepositoryService
from app.repo_mgmt.services.repo_resolver import RepoResolver
from MCP.services.envelope import McpEnvelope


class McpQueryService:
    """面向对象封装的 MCP 查询门面。"""

    DEFAULT_TIMEOUT_MS = 60000
    DEFAULT_TOP_K = 10
    DEFAULT_GRAPH_LIMIT = 20

    @staticmethod
    def normalize_paths(path: str, extra_paths: Optional[Sequence[str]] = None) -> tuple[str, ...]:
        items: List[str] = []
        raw = (path or "").strip()
        if raw:
            items.append(raw)
        for item in extra_paths or []:
            text = str(item or "").strip()
            if text:
                items.append(text)
        if not items:
            raise click.ClickException("至少指定一个 path")
        return tuple(items)

    @classmethod
    def _timeout(cls, timeout_ms: Optional[int]) -> int:
        if timeout_ms is None:
            return cls.DEFAULT_TIMEOUT_MS
        return max(0, int(timeout_ms))

    @classmethod
    def _top_k(cls, top_k: Optional[int]) -> int:
        if top_k is None:
            return cls.DEFAULT_TOP_K
        return max(1, int(top_k))

    @staticmethod
    def _assert_kind_code(repo) -> None:
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind != RepoKind.CODE:
            raise click.ClickException(f"该查询仅支持 kind=code，当前 kind={kind}")

    @staticmethod
    def _assert_kind_lib(repo) -> None:
        kind = getattr(repo, "kind", None) or RepoKind.CODE
        if kind != RepoKind.LIB:
            raise click.ClickException(f"search api 仅支持 kind=lib，当前 kind={kind}")

    @staticmethod
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

    @classmethod
    async def _expand_target_paths(
        cls,
        paths: tuple[str, ...],
        *,
        kind: Optional[str] = None,
    ) -> list[str]:
        repos = await resolve_search_repos(paths, kind=kind)
        return [RepoResolver.normalize_repo_path(r.local_path) for r in repos if r.local_path]

    @classmethod
    def doctor(cls) -> Dict[str, object]:
        """环境自检。"""
        try:
            return run_async(DoctorService.run)
        except Exception as exc:
            return McpEnvelope.from_exception(exc)

    @classmethod
    def repo_list(cls) -> Dict[str, object]:
        """列出已登记仓库。"""

        async def _list() -> Dict[str, object]:
            async with get_db_session() as db:
                repos, total = await GitRepositoryService.get_repository_list(
                    db,
                    DEFAULT_USER_ID,
                    page=1,
                    page_size=1000,
                )
            items = [repo_public_view(r) for r in repos]
            return {"total": int(total or len(items)), "items": items}

        return McpEnvelope.run(_list, timeout_ms=0)

    @classmethod
    def resolve(
        cls,
        path: str,
        query: str,
        *,
        extra_paths: Optional[Sequence[str]] = None,
        intent: str = "auto",
        top_k: Optional[int] = None,
        timeout_ms: Optional[int] = None,
        with_content: bool = True,
    ) -> Dict[str, object]:
        """统一检索编排（主入口）。"""
        try:
            paths = cls.normalize_paths(path, extra_paths)
        except click.ClickException as exc:
            return McpEnvelope.from_exception(exc)
        limit = cls._top_k(top_k)
        wait_ms = cls._timeout(timeout_ms)

        async def _resolve() -> dict:
            from app.repo_analysis.services.search_resolve import SearchResolveService

            targets = await cls._expand_target_paths(paths)

            async def _one(repo_path: str):
                repo = await get_repo_by_path(repo_path)
                try:
                    result = await SearchResolveService.resolve(
                        repo_id=repo.id,
                        query=query,
                        top_k=limit,
                        intent=intent,
                    )
                except ValueError as e:
                    raise click.ClickException(str(e)) from e
                result["path"] = repo_path
                result["kind"] = getattr(repo, "kind", None) or RepoKind.CODE
                return result

            try:
                return await MultiPathSearchService.fanout(
                    targets,
                    top_k=limit,
                    run_one=_one,
                    query_fields={"query": query, "path_queries": list(paths)},
                )
            except ValueError as e:
                raise click.ClickException(str(e)) from e

        return McpEnvelope.run(
            _resolve,
            timeout_ms=wait_ms,
            profile=ResponseScheme.PROFILE_RESOLVE,
            postprocess=lambda out: SearchSnippetAttacher.attach_to_payload(out, enabled=with_content),
        )

    @classmethod
    def similar(
        cls,
        path: str,
        code: str,
        *,
        extra_paths: Optional[Sequence[str]] = None,
        top_k: Optional[int] = None,
        timeout_ms: Optional[int] = None,
        with_content: bool = True,
    ) -> Dict[str, object]:
        """相似代码片段检索。"""
        try:
            paths = cls.normalize_paths(path, extra_paths)
        except click.ClickException as exc:
            return McpEnvelope.from_exception(exc)
        limit = cls._top_k(top_k)
        wait_ms = cls._timeout(timeout_ms)

        async def _similar() -> dict:
            targets = await cls._expand_target_paths(paths, kind=RepoKind.CODE)

            async def _one(repo_path: str):
                repo = await get_repo_by_path(repo_path)
                cls._assert_kind_code(repo)
                result = await SearchService.search_similar_code(
                    repo_id=repo.id,
                    code_text=code,
                    top_k=limit,
                )
                result["path"] = repo_path
                result["kind"] = RepoKind.CODE
                result["repo_id"] = repo.id
                return result

            try:
                return await MultiPathSearchService.fanout(
                    targets,
                    top_k=limit,
                    run_one=_one,
                    query_fields={"path_queries": list(paths)},
                )
            except ValueError as e:
                raise click.ClickException(str(e)) from e

        return McpEnvelope.run(
            _similar,
            timeout_ms=wait_ms,
            postprocess=lambda out: SearchSnippetAttacher.attach_to_payload(out, enabled=with_content),
        )

    @classmethod
    def related(
        cls,
        path: str,
        keywords: str,
        *,
        extra_paths: Optional[Sequence[str]] = None,
        top_k: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        """相关文件/符号定位。"""
        try:
            paths = cls.normalize_paths(path, extra_paths)
            keyword_list = [k.strip() for k in str(keywords or "").split(",") if k.strip()]
            if not keyword_list:
                raise click.ClickException("keywords 不能为空")
        except click.ClickException as exc:
            return McpEnvelope.from_exception(exc)
        limit = cls._top_k(top_k)
        wait_ms = cls._timeout(timeout_ms)

        async def _related() -> dict:
            targets = await cls._expand_target_paths(paths, kind=RepoKind.CODE)

            async def _one(repo_path: str):
                repo = await get_repo_by_path(repo_path)
                cls._assert_kind_code(repo)
                result = await SearchService.search_related_files(
                    repo_id=repo.id,
                    keywords=keyword_list,
                    top_k=limit,
                )
                result["path"] = repo_path
                result["kind"] = RepoKind.CODE
                result["repo_id"] = repo.id
                return result

            try:
                return await MultiPathSearchService.fanout(
                    targets,
                    top_k=limit,
                    run_one=_one,
                    query_fields={"keywords": keyword_list, "path_queries": list(paths)},
                )
            except ValueError as e:
                raise click.ClickException(str(e)) from e

        return McpEnvelope.run(_related, timeout_ms=wait_ms)

    @classmethod
    def pattern(
        cls,
        path: str,
        query: str,
        *,
        extra_paths: Optional[Sequence[str]] = None,
        top_k: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        """历史经验模式检索。"""
        try:
            paths = cls.normalize_paths(path, extra_paths)
        except click.ClickException as exc:
            return McpEnvelope.from_exception(exc)
        limit = cls._top_k(top_k)
        wait_ms = cls._timeout(timeout_ms)

        async def _pattern() -> dict:
            targets = await cls._expand_target_paths(paths, kind=RepoKind.CODE)

            async def _one(repo_path: str):
                repo = await get_repo_by_path(repo_path)
                cls._assert_kind_code(repo)
                result = await SearchService.search_patterns(
                    repo_id=repo.id,
                    query=query,
                    top_k=limit,
                )
                result["path"] = repo_path
                result["kind"] = RepoKind.CODE
                result["repo_id"] = repo.id
                return result

            try:
                return await MultiPathSearchService.fanout(
                    targets,
                    top_k=limit,
                    run_one=_one,
                    query_fields={"query": query, "path_queries": list(paths)},
                )
            except ValueError as e:
                raise click.ClickException(str(e)) from e

        return McpEnvelope.run(_pattern, timeout_ms=wait_ms)

    @classmethod
    def api(
        cls,
        path: str,
        query: str,
        *,
        extra_paths: Optional[Sequence[str]] = None,
        top_k: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        """Lib 公开 API 检索。"""
        try:
            paths = cls.normalize_paths(path, extra_paths)
        except click.ClickException as exc:
            return McpEnvelope.from_exception(exc)
        limit = cls._top_k(top_k)
        wait_ms = cls._timeout(timeout_ms)

        async def _api() -> dict:
            from app.lib_analysis.services.search_service import LibSearchService

            targets = await cls._expand_target_paths(paths, kind=RepoKind.LIB)

            async def _one(repo_path: str):
                repo = await get_repo_by_path(repo_path)
                cls._assert_kind_lib(repo)
                result = await LibSearchService.search_apis(
                    repo_id=repo.id,
                    query=query,
                    top_k=limit,
                )
                result["path"] = repo_path
                result["kind"] = RepoKind.LIB
                result["repo_id"] = repo.id
                return result

            try:
                return await MultiPathSearchService.fanout(
                    targets,
                    top_k=limit,
                    run_one=_one,
                    query_fields={"query": query, "path_queries": list(paths)},
                )
            except ValueError as e:
                raise click.ClickException(str(e)) from e

        return McpEnvelope.run(_api, timeout_ms=wait_ms)

    @classmethod
    def dependents(
        cls,
        path: str,
        file_path: str,
        *,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        """查询依赖指定文件的其它文件。"""
        wait_ms = cls._timeout(timeout_ms)

        async def _dependents() -> dict:
            repo = await get_repo_by_path(path)
            cls._assert_kind_code(repo)
            with CodeGraphGateway.create_search() as q:
                res = await q.query_dependents_of_file(repo.id, file_path)
            if not res.result:
                raise click.ClickException(res.message or "查询失败")
            content = dict(res.content or {})
            deps = list(content.get("dependents") or [])
            items = cls._graph_file_items(deps, relation="dependents")
            return {
                "path": RepoResolver.normalize_repo_path(path),
                "repo_id": repo.id,
                "kind": RepoKind.CODE,
                "file": file_path,
                "total": len(items),
                "items": items,
                "dependents": deps,
            }

        return McpEnvelope.run(_dependents, timeout_ms=wait_ms)

    @classmethod
    def dependencies(
        cls,
        path: str,
        file_path: str,
        *,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        """查询指定文件依赖的其它文件。"""
        wait_ms = cls._timeout(timeout_ms)

        async def _dependencies() -> dict:
            repo = await get_repo_by_path(path)
            cls._assert_kind_code(repo)
            with CodeGraphGateway.create_search() as q:
                res = await q.query_dependented_of_file(repo.id, file_path)
            if not res.result:
                raise click.ClickException(res.message or "查询失败")
            content = dict(res.content or {})
            deps = list(content.get("dependented") or content.get("dependencies") or [])
            items = cls._graph_file_items(deps, relation="dependencies")
            return {
                "path": RepoResolver.normalize_repo_path(path),
                "repo_id": repo.id,
                "kind": RepoKind.CODE,
                "file": file_path,
                "total": len(items),
                "items": items,
                "dependencies": deps,
            }

        return McpEnvelope.run(_dependencies, timeout_ms=wait_ms)

    @classmethod
    def callers(
        cls,
        path: str,
        symbol: str,
        *,
        extra_paths: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        """查询调用指定符号的 callers。"""
        try:
            paths = cls.normalize_paths(path, extra_paths)
        except click.ClickException as exc:
            return McpEnvelope.from_exception(exc)
        graph_limit = max(1, int(limit or cls.DEFAULT_GRAPH_LIMIT))
        wait_ms = cls._timeout(timeout_ms)

        async def _callers() -> dict:
            targets = await cls._expand_target_paths(paths, kind=RepoKind.CODE)

            async def _one(repo_path: str):
                repo = await get_repo_by_path(repo_path)
                cls._assert_kind_code(repo)
                with CodeGraphGateway.create_search() as q:
                    res = await q.query_callers_of_symbol(repo.id, symbol, limit=graph_limit)
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
                    "path": repo_path,
                    "repo_id": repo.id,
                    "kind": RepoKind.CODE,
                    "total": len(items),
                    "items": items,
                }

            try:
                return await MultiPathSearchService.fanout(
                    targets,
                    top_k=graph_limit,
                    run_one=_one,
                    query_fields={"symbol": symbol, "path_queries": list(paths)},
                )
            except ValueError as e:
                raise click.ClickException(str(e)) from e

        return McpEnvelope.run(_callers, timeout_ms=wait_ms)

    @classmethod
    def callees(
        cls,
        path: str,
        symbol: str,
        *,
        extra_paths: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, object]:
        """查询指定符号调用的 callees。"""
        try:
            paths = cls.normalize_paths(path, extra_paths)
        except click.ClickException as exc:
            return McpEnvelope.from_exception(exc)
        graph_limit = max(1, int(limit or cls.DEFAULT_GRAPH_LIMIT))
        wait_ms = cls._timeout(timeout_ms)

        async def _callees() -> dict:
            targets = await cls._expand_target_paths(paths, kind=RepoKind.CODE)

            async def _one(repo_path: str):
                repo = await get_repo_by_path(repo_path)
                cls._assert_kind_code(repo)
                with CodeGraphGateway.create_search() as q:
                    res = await q.query_callees_of_symbol(repo.id, symbol, limit=graph_limit)
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
                    "path": repo_path,
                    "repo_id": repo.id,
                    "kind": RepoKind.CODE,
                    "total": len(items),
                    "items": items,
                }

            try:
                return await MultiPathSearchService.fanout(
                    targets,
                    top_k=graph_limit,
                    run_one=_one,
                    query_fields={"symbol": symbol, "path_queries": list(paths)},
                )
            except ValueError as e:
                raise click.ClickException(str(e)) from e

        return McpEnvelope.run(_callees, timeout_ms=wait_ms)
