"""场景会话：共享本仓登记 / CodeGraph / 向量分析状态。"""
from __future__ import annotations
import asyncio
from tests.scenarios.base import CodebaseScenarioBase


class ScenarioSession(CodebaseScenarioBase):
    """可复用会话：减少重复 analyze / init。"""

    CLEAR_BEFORE_ANALYZE = False
    ANALYZE_TARGET = "app/repo_analysis"
    ANALYZE_TIMEOUT_SEC = 420
    POLL_INTERVAL_SEC = 3
    _graph_ready: bool = False
    _vector_ready: bool = False
    _loop = None

    @classmethod
    def run_async(cls, coro):
        """复用同一事件循环，避免调度器 Lock 绑定到已关闭的 loop。"""
        if ScenarioSession._loop is None or ScenarioSession._loop.is_closed():
            ScenarioSession._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ScenarioSession._loop)
        return ScenarioSession._loop.run_until_complete(coro)

    @classmethod
    async def shutdown_runtime(cls) -> None:
        await super().shutdown_runtime()
        ScenarioSession._graph_ready = False
        ScenarioSession._vector_ready = False
        ScenarioSession._repo_id = None
        ScenarioSession._repo_path = None
        if ScenarioSession._loop is not None and not ScenarioSession._loop.is_closed():
            ScenarioSession._loop.close()
        ScenarioSession._loop = None
        ScenarioSession._lock = None
        ScenarioSession._lock_loop_id = None

    @classmethod
    def _async_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = getattr(ScenarioSession, "_lock", None)
        if lock is None or getattr(ScenarioSession, "_lock_loop_id", None) != id(loop):
            ScenarioSession._lock = asyncio.Lock()
            ScenarioSession._lock_loop_id = id(loop)
        return ScenarioSession._lock

    @classmethod
    async def ensure_repo(cls) -> str:
        if ScenarioSession._repo_id and ScenarioSession._repo_path:
            cls.apply_feature_flags()
            import app.runtime as runtime_mod
            if not getattr(runtime_mod, "_runtime_inited", False):
                await cls._reset_runtime()
            cls._repo_id = ScenarioSession._repo_id
            cls._repo_path = ScenarioSession._repo_path
            return ScenarioSession._repo_id
        repo_id = await super().ensure_repo()
        ScenarioSession._repo_id = repo_id
        ScenarioSession._repo_path = cls._repo_path
        return repo_id

    @classmethod
    async def ensure_vector_ready(cls) -> str:
        async with cls._async_lock():
            need_clear = bool(cls.CLEAR_BEFORE_ANALYZE) and not ScenarioSession._vector_ready
            repo_id = await cls.ensure_repo()
            if not ScenarioSession._vector_ready:
                from app.repo_analysis.services.analysis_service import AnalysisService
                from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
                from app.repo_analysis.services.file_analysis_service import FileAnalysisService

                CodeGraphGateway.ensure_ready()
                print(
                    f"[scenario] vector analyze start target={cls.ANALYZE_TARGET} "
                    f"clear={need_clear}",
                    flush=True,
                )
                # 先停调度再清库，避免 SQLite database is locked
                await FileAnalysisService.stop_global_scheduler()
                try:
                    await AnalysisService.stop_scan(repo_id, reason="scenario reset")
                except Exception:
                    pass
                if need_clear:
                    await AnalysisService.delete_repo_analysis_data(repo_id)
                FileAnalysisService.start_global_scheduler()
                prev_clear = cls.CLEAR_BEFORE_ANALYZE
                cls.CLEAR_BEFORE_ANALYZE = False
                try:
                    summary = await cls.run_analyze()
                finally:
                    cls.CLEAR_BEFORE_ANALYZE = prev_clear
                a = summary.get("analysis_summary") or {}
                print(
                    f"[scenario] vector analyze done completed={a.get('completed_files')} "
                    f"failed={a.get('failed_files')}",
                    flush=True,
                )
                ScenarioSession._vector_ready = True
            return repo_id

    @classmethod
    async def ensure_graph_ready(cls) -> str:
        async with cls._async_lock():
            repo_id = await cls.ensure_repo()
            if not ScenarioSession._graph_ready:
                from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
                CodeGraphGateway.ensure_ready()
                generator = CodeGraphGateway.create_generator(
                    repo_id=repo_id,
                    repo_name="Moma-CodeBase",
                    repo_local_path=str(cls.codebase_path()),
                )
                try:
                    await generator.generate_graph(clean_stale=False)
                finally:
                    generator.close()
                ScenarioSession._graph_ready = True
            return repo_id

    @classmethod
    async def query_dependents(cls, file_path: str):
        repo_id = await cls.ensure_graph_ready()
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
        with CodeGraphGateway.create_search() as search:
            return await search.query_dependents_of_file(repo_id, file_path)

    @classmethod
    async def query_dependencies(cls, file_path: str):
        repo_id = await cls.ensure_graph_ready()
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
        with CodeGraphGateway.create_search() as search:
            return await search.query_dependented_of_file(repo_id, file_path)

    @classmethod
    async def query_file_summary(cls, file_path: str):
        repo_id = await cls.ensure_graph_ready()
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
        with CodeGraphGateway.create_search() as search:
            return await search.query_file_summary(repo_id, [file_path])

    @classmethod
    async def query_callers(cls, symbol: str, limit: int = 30):
        repo_id = await cls.ensure_graph_ready()
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
        with CodeGraphGateway.create_search() as search:
            return await search.query_callers_of_symbol(repo_id, symbol, limit=limit)

    @classmethod
    async def query_callees(cls, symbol: str, limit: int = 30):
        repo_id = await cls.ensure_graph_ready()
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
        with CodeGraphGateway.create_search() as search:
            return await search.query_callees_of_symbol(repo_id, symbol, limit=limit)
