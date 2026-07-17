"""Pando-Agent 外部仓场景会话。"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import pytest
from tests.scenarios.base import CodebaseScenarioBase


DEFAULT_PANDO_PATH = Path(r"F:\Product_Dev\PANDO\Pando-Agent")


class PandoAgentScenarioSession(CodebaseScenarioBase):
    """登记并分析外部 Pando-Agent 仓（与本仓 ScenarioSession 隔离）。"""

    ENABLE_SYMBOL_SUMMARY = True
    ENABLE_CODE_GRAPH = True
    # 全仓产品代码（app/），不是某个业务子目录；排除前端/打包等噪音
    ANALYZE_TARGET = "app"
    CLEAR_BEFORE_ANALYZE = False
    ANALYZE_TIMEOUT_SEC = 7200
    POLL_INTERVAL_SEC = 5
    # SQLite + LLM 摘要时过高并发易 database is locked；场景侧压到 4
    FILE_WORKER_COUNT = 4
    EXTRA_EXCLUDED_DIRS = {
        "website",
        "packaging",
        "alembic",
        "repos",
        "data",
        "scripts",
        "node_modules",
        ".venv",
        ".pytest_cache",
        "参考项目",
    }

    @classmethod
    def _should_clear(cls) -> bool:
        return os.environ.get("PANDO_CLEAR", "").strip() in {"1", "true", "True"}

    @classmethod
    def apply_feature_flags(cls) -> None:
        super().apply_feature_flags()
        from app.repo_analysis.services.analysis_service import AnalysisService

        AnalysisService.EXCLUDED_DIRS = set(AnalysisService.EXCLUDED_DIRS) | set(cls.EXTRA_EXCLUDED_DIRS)

    _loop = None
    _vector_ready: bool = False
    _graph_ready: bool = False
    _session_repo_id = None
    _session_repo_path = None

    @classmethod
    def codebase_path(cls) -> Path:
        raw = (os.environ.get("PANDO_AGENT_PATH") or "").strip()
        path = Path(raw) if raw else DEFAULT_PANDO_PATH
        return path.resolve()

    @classmethod
    def require_repo_or_skip(cls) -> Path:
        path = cls.codebase_path()
        if not path.is_dir():
            pytest.skip(f"Pando-Agent 仓不存在: {path}")
        if not (path / "app").is_dir():
            pytest.skip(f"缺少 app 目录: {path}")
        return path

    @classmethod
    def run_async(cls, coro):
        if PandoAgentScenarioSession._loop is None or PandoAgentScenarioSession._loop.is_closed():
            PandoAgentScenarioSession._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(PandoAgentScenarioSession._loop)
        return PandoAgentScenarioSession._loop.run_until_complete(coro)

    @classmethod
    def _async_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = getattr(PandoAgentScenarioSession, "_lock", None)
        if lock is None or getattr(PandoAgentScenarioSession, "_lock_loop_id", None) != id(loop):
            PandoAgentScenarioSession._lock = asyncio.Lock()
            PandoAgentScenarioSession._lock_loop_id = id(loop)
        return PandoAgentScenarioSession._lock

    @classmethod
    async def ensure_repo(cls) -> str:
        cls.require_repo_or_skip()
        if PandoAgentScenarioSession._session_repo_id and PandoAgentScenarioSession._session_repo_path:
            cls.apply_feature_flags()
            import app.runtime as runtime_mod
            if not getattr(runtime_mod, "_runtime_inited", False):
                await cls._reset_runtime()
            cls._repo_id = PandoAgentScenarioSession._session_repo_id
            cls._repo_path = PandoAgentScenarioSession._session_repo_path
            return PandoAgentScenarioSession._session_repo_id
        repo_id = await super().ensure_repo()
        PandoAgentScenarioSession._session_repo_id = repo_id
        PandoAgentScenarioSession._session_repo_path = cls._repo_path
        return repo_id

    @classmethod
    async def ensure_vector_ready(cls) -> str:
        async with cls._async_lock():
            need_clear = bool(cls._should_clear() or cls.CLEAR_BEFORE_ANALYZE) and not PandoAgentScenarioSession._vector_ready
            repo_id = await cls.ensure_repo()
            if not PandoAgentScenarioSession._vector_ready:
                from app.repo_analysis.services.analysis_service import AnalysisService
                from app.repo_analysis.services.file_analysis_service import FileAnalysisService

                print(
                    f"[pando-scenario] analyze start path={cls.codebase_path()} "
                    f"target={cls.ANALYZE_TARGET} symbol_summary={cls.ENABLE_SYMBOL_SUMMARY} "
                    f"clear={need_clear}",
                    flush=True,
                )
                await FileAnalysisService.stop_global_scheduler()
                try:
                    await AnalysisService.stop_scan(repo_id, reason="pando scenario reset")
                except Exception:
                    pass
                if need_clear:
                    await AnalysisService.delete_repo_analysis_data(repo_id)
                FileAnalysisService.start_global_scheduler(
                    interval_seconds=2.0,
                    worker_count=cls.FILE_WORKER_COUNT,
                )
                prev = cls.CLEAR_BEFORE_ANALYZE
                cls.CLEAR_BEFORE_ANALYZE = False
                try:
                    summary = await cls.run_analyze()
                finally:
                    cls.CLEAR_BEFORE_ANALYZE = prev
                a = summary.get("analysis_summary") or {}
                completed = int(a.get("completed_files") or 0)
                if completed <= 0:
                    print("[pando-scenario] no completed files, force clear re-analyze", flush=True)
                    await FileAnalysisService.stop_global_scheduler()
                    await AnalysisService.delete_repo_analysis_data(repo_id)
                    FileAnalysisService.start_global_scheduler(
                        interval_seconds=2.0,
                        worker_count=cls.FILE_WORKER_COUNT,
                    )
                    summary = await cls.run_analyze()
                    a = summary.get("analysis_summary") or {}
                print(
                    f"[pando-scenario] analyze done completed={a.get('completed_files')} "
                    f"failed={a.get('failed_files')}",
                    flush=True,
                )
                if cls.ENABLE_CODE_GRAPH:
                    await cls._wait_code_graph(repo_id)
                    PandoAgentScenarioSession._graph_ready = True
                PandoAgentScenarioSession._vector_ready = True
            return repo_id

    @classmethod
    async def ensure_graph_ready(cls) -> str:
        """仅保证 CodeGraph 索引可用（不强制向量 analyze）。"""
        async with cls._async_lock():
            repo_id = await cls.ensure_repo()
            if not PandoAgentScenarioSession._graph_ready:
                from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway

                CodeGraphGateway.ensure_ready()
                await cls._wait_code_graph(repo_id)
                PandoAgentScenarioSession._graph_ready = True
            return repo_id

    @classmethod
    async def query_callers(cls, symbol: str, limit: int = 30):
        repo_id = await cls.ensure_graph_ready()
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway

        with CodeGraphGateway.create_search() as search:
            return await search.query_callers_of_symbol(repo_id, symbol, limit=limit)

    @classmethod
    async def query_dependents(cls, file_path: str):
        repo_id = await cls.ensure_graph_ready()
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway

        with CodeGraphGateway.create_search() as search:
            return await search.query_dependents_of_file(repo_id, file_path)

    @classmethod
    async def _wait_code_graph(cls, repo_id: str, *, timeout_sec: float = 1800) -> None:
        """等待 analyze 触发的 CodeGraph 任务；若无任务则主动全量 init。"""
        from app.config.settings import settings
        from app.repo_analysis.services.analysis_service import AnalysisService
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway

        settings.code_graph_enabled = True
        task = AnalysisService._running_graph_tasks.get(repo_id)
        if task and not task.done():
            print("[pando-scenario] waiting CodeGraph task...", flush=True)
            await asyncio.wait_for(task, timeout=timeout_sec)
        repo_path = str(PandoAgentScenarioSession._session_repo_path or cls.codebase_path())
        graph_dir = Path(repo_path) / ".codegraph"
        if graph_dir.is_dir():
            print(f"[pando-scenario] CodeGraph ready path={graph_dir}", flush=True)
            return
        print(f"[pando-scenario] CodeGraph missing, force init path={repo_path}", flush=True)
        generator = CodeGraphGateway.create_generator(
            repo_id=repo_id,
            repo_name=str(repo_id),
            repo_local_path=repo_path,
        )
        try:
            await generator.generate_graph(clean_stale=True)
        finally:
            generator.close()
        if not graph_dir.is_dir():
            raise AssertionError(f"CodeGraph init 后仍无 .codegraph: {graph_dir}")
        print(f"[pando-scenario] CodeGraph init done path={graph_dir}", flush=True)

    @classmethod
    async def shutdown_runtime(cls) -> None:
        await super().shutdown_runtime()
        PandoAgentScenarioSession._vector_ready = False
        PandoAgentScenarioSession._graph_ready = False
        PandoAgentScenarioSession._session_repo_id = None
        PandoAgentScenarioSession._session_repo_path = None
        if PandoAgentScenarioSession._loop is not None and not PandoAgentScenarioSession._loop.is_closed():
            PandoAgentScenarioSession._loop.close()
        PandoAgentScenarioSession._loop = None
        PandoAgentScenarioSession._lock = None
        PandoAgentScenarioSession._lock_loop_id = None
