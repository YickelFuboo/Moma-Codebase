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
    ENABLE_CODE_GRAPH = False
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
        if cls._loop is None or cls._loop.is_closed():
            cls._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(cls._loop)
        return cls._loop.run_until_complete(coro)

    @classmethod
    def _async_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = getattr(cls, "_lock", None)
        if lock is None or getattr(cls, "_lock_loop_id", None) != id(loop):
            cls._lock = asyncio.Lock()
            cls._lock_loop_id = id(loop)
        return cls._lock

    @classmethod
    async def ensure_repo(cls) -> str:
        cls.require_repo_or_skip()
        if cls._session_repo_id and cls._session_repo_path:
            cls.apply_feature_flags()
            import app.runtime as runtime_mod
            if not getattr(runtime_mod, "_runtime_inited", False):
                await cls._reset_runtime()
            cls._repo_id = cls._session_repo_id
            cls._repo_path = cls._session_repo_path
            return cls._session_repo_id
        repo_id = await super().ensure_repo()
        cls._session_repo_id = repo_id
        cls._session_repo_path = cls._repo_path
        return repo_id

    @classmethod
    async def ensure_vector_ready(cls) -> str:
        async with cls._async_lock():
            need_clear = bool(cls._should_clear() or cls.CLEAR_BEFORE_ANALYZE) and not cls._vector_ready
            repo_id = await cls.ensure_repo()
            if not cls._vector_ready:
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
                    # 无缓存时再强制清空重跑一次
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
                cls._vector_ready = True
            return repo_id

    @classmethod
    async def shutdown_runtime(cls) -> None:
        await super().shutdown_runtime()
        cls._vector_ready = False
        cls._session_repo_id = None
        cls._session_repo_path = None
        if cls._loop is not None and not cls._loop.is_closed():
            cls._loop.close()
        cls._loop = None
        cls._lock = None
        cls._lock_loop_id = None
