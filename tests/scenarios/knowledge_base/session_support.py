"""KnowledegBase-Service 外部仓场景会话。"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import pytest
from tests.scenarios.base import CodebaseScenarioBase


DEFAULT_KB_REF = Path(__file__).resolve().parents[3] / "参考" / "KnowledegBase-Service"
DEFAULT_KB_SRC = Path(r"F:\Product_Dev\KnowledegBase-Service")


class KnowledgeBaseScenarioSession(CodebaseScenarioBase):
    """登记并分析 KnowledegBase-Service（与本仓 / Pando 会话隔离）。

    默认优先已登记源路径；参考/ 下为镜像副本（便于离线对照）。
    """

    ENABLE_SYMBOL_SUMMARY = True
    ENABLE_CODE_GRAPH = True
    # 产品全仓 app/（用户要求成功 analyze 按全仓）
    ANALYZE_TARGET = "app"
    CLEAR_BEFORE_ANALYZE = False
    ANALYZE_TIMEOUT_SEC = 7200
    POLL_INTERVAL_SEC = 5
    FILE_WORKER_COUNT = 10
    EXTRA_EXCLUDED_DIRS = {
        "alembic",
        "data",
        "scripts",
        "node_modules",
        ".venv",
        ".pytest_cache",
        "参考项目",
        "参考",
        "res",
    }

    _loop = None
    _vector_ready: bool = False
    _session_repo_id = None
    _session_repo_path = None

    @classmethod
    def _should_clear(cls) -> bool:
        return os.environ.get("KB_CLEAR", "").strip() in {"1", "true", "True"}

    @classmethod
    def apply_feature_flags(cls) -> None:
        super().apply_feature_flags()
        from app.repo_analysis.services.analysis_service import AnalysisService

        AnalysisService.EXCLUDED_DIRS = set(AnalysisService.EXCLUDED_DIRS) | set(cls.EXTRA_EXCLUDED_DIRS)

    @classmethod
    def codebase_path(cls) -> Path:
        raw = (os.environ.get("KB_SERVICE_PATH") or "").strip()
        if raw:
            return Path(raw).resolve()
        # 优先已登记源仓，保证 analyze/检索与现有 repo_id 对齐；参考/ 为副本
        if DEFAULT_KB_SRC.is_dir() and (DEFAULT_KB_SRC / "app").is_dir():
            return DEFAULT_KB_SRC.resolve()
        if DEFAULT_KB_REF.is_dir() and (DEFAULT_KB_REF / "app").is_dir():
            return DEFAULT_KB_REF.resolve()
        return DEFAULT_KB_SRC.resolve()

    @classmethod
    def require_repo_or_skip(cls) -> Path:
        path = cls.codebase_path()
        if not path.is_dir():
            pytest.skip(f"KnowledegBase-Service 仓不存在: {path}")
        if not (path / "app").is_dir():
            pytest.skip(f"缺少 app 目录: {path}")
        return path

    @classmethod
    def run_async(cls, coro):
        if KnowledgeBaseScenarioSession._loop is None or KnowledgeBaseScenarioSession._loop.is_closed():
            KnowledgeBaseScenarioSession._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(KnowledgeBaseScenarioSession._loop)
        return KnowledgeBaseScenarioSession._loop.run_until_complete(coro)

    @classmethod
    def _async_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = getattr(KnowledgeBaseScenarioSession, "_lock", None)
        if lock is None or getattr(KnowledgeBaseScenarioSession, "_lock_loop_id", None) != id(loop):
            KnowledgeBaseScenarioSession._lock = asyncio.Lock()
            KnowledgeBaseScenarioSession._lock_loop_id = id(loop)
        return KnowledgeBaseScenarioSession._lock

    @classmethod
    async def ensure_repo(cls) -> str:
        cls.require_repo_or_skip()
        if KnowledgeBaseScenarioSession._session_repo_id and KnowledgeBaseScenarioSession._session_repo_path:
            cls.apply_feature_flags()
            import app.runtime as runtime_mod
            if not getattr(runtime_mod, "_runtime_inited", False):
                await cls._reset_runtime()
            cls._repo_id = KnowledgeBaseScenarioSession._session_repo_id
            cls._repo_path = KnowledgeBaseScenarioSession._session_repo_path
            return KnowledgeBaseScenarioSession._session_repo_id
        repo_id = await super().ensure_repo()
        KnowledgeBaseScenarioSession._session_repo_id = repo_id
        KnowledgeBaseScenarioSession._session_repo_path = cls._repo_path
        return repo_id

    @classmethod
    async def ensure_vector_ready(cls) -> str:
        async with cls._async_lock():
            need_clear = bool(cls._should_clear() or cls.CLEAR_BEFORE_ANALYZE) and not KnowledgeBaseScenarioSession._vector_ready
            repo_id = await cls.ensure_repo()
            if not KnowledgeBaseScenarioSession._vector_ready:
                from app.repo_analysis.services.analysis_service import AnalysisService
                from app.repo_analysis.services.file_analysis_service import FileAnalysisService

                print(
                    f"[kb-scenario] analyze start path={cls.codebase_path()} "
                    f"target={cls.ANALYZE_TARGET} symbol_summary={cls.ENABLE_SYMBOL_SUMMARY} "
                    f"clear={need_clear}",
                    flush=True,
                )
                await FileAnalysisService.stop_global_scheduler()
                try:
                    await AnalysisService.stop_scan(repo_id, reason="kb scenario reset")
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
                    print("[kb-scenario] no completed files, force clear re-analyze", flush=True)
                    await FileAnalysisService.stop_global_scheduler()
                    await AnalysisService.delete_repo_analysis_data(repo_id)
                    FileAnalysisService.start_global_scheduler(
                        interval_seconds=2.0,
                        worker_count=cls.FILE_WORKER_COUNT,
                    )
                    summary = await cls.run_analyze()
                    a = summary.get("analysis_summary") or {}
                print(
                    f"[kb-scenario] analyze done completed={a.get('completed_files')} "
                    f"failed={a.get('failed_files')}",
                    flush=True,
                )
                KnowledgeBaseScenarioSession._vector_ready = True
            return repo_id

    @classmethod
    async def shutdown_runtime(cls) -> None:
        await super().shutdown_runtime()
        KnowledgeBaseScenarioSession._vector_ready = False
        KnowledgeBaseScenarioSession._session_repo_id = None
        KnowledgeBaseScenarioSession._session_repo_path = None
        if KnowledgeBaseScenarioSession._loop is not None and not KnowledgeBaseScenarioSession._loop.is_closed():
            KnowledgeBaseScenarioSession._loop.close()
        KnowledgeBaseScenarioSession._loop = None
        KnowledgeBaseScenarioSession._lock = None
        KnowledgeBaseScenarioSession._lock_loop_id = None
