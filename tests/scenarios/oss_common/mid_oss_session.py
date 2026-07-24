"""中等开源仓 scenario 会话基类：登记路径 + 按需清库分析。"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import ClassVar, Optional, Set
import pytest
from tests.scenarios.base import CodebaseScenarioBase


class MidOssScenarioSession(CodebaseScenarioBase):
    """子类覆盖 DEFAULT_PATH / PATH_ENV / CLEAR_ENV / TAG / EXTRA_EXCLUDED_DIRS。"""

    ENABLE_SYMBOL_SUMMARY = True
    ENABLE_CODE_GRAPH = False
    ANALYZE_TARGET = ""
    CLEAR_BEFORE_ANALYZE = False
    ANALYZE_TIMEOUT_SEC = 7200
    POLL_INTERVAL_SEC = 5
    FILE_WORKER_COUNT = 10

    DEFAULT_PATH: ClassVar[Path]
    PATH_ENV: ClassVar[str] = ""
    CLEAR_ENV: ClassVar[str] = ""
    TAG: ClassVar[str] = "mid-oss"
    EXTRA_EXCLUDED_DIRS: ClassVar[Set[str]] = {
        ".git",
        "node_modules",
        "vendor",
        "docs",
        "testdata",
    }
    REQUIRE_MARKERS: ClassVar[tuple[str, ...]] = ()

    _loop = None
    _vector_ready: bool = False
    _session_repo_id = None
    _session_repo_path = None

    @classmethod
    def _should_clear(cls) -> bool:
        return os.environ.get(cls.CLEAR_ENV, "").strip() in {"1", "true", "True"}

    @classmethod
    def apply_feature_flags(cls) -> None:
        super().apply_feature_flags()
        from app.repo_analysis.services.analysis_service import AnalysisService

        AnalysisService.EXCLUDED_DIRS = set(AnalysisService.EXCLUDED_DIRS) | set(
            cls.EXTRA_EXCLUDED_DIRS
        )

    @classmethod
    def codebase_path(cls) -> Path:
        raw = (os.environ.get(cls.PATH_ENV) or "").strip()
        if raw:
            return Path(raw).resolve()
        return Path(cls.DEFAULT_PATH).resolve()

    @classmethod
    def require_repo_or_skip(cls) -> Path:
        path = cls.codebase_path()
        if not path.is_dir():
            pytest.skip(f"{cls.TAG} 仓不存在: {path}")
        for marker in cls.REQUIRE_MARKERS:
            if not (path / marker).exists():
                pytest.skip(f"{cls.TAG} 缺少 {marker}: {path}")
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

                target = cls.ANALYZE_TARGET or "(repo root)"
                print(
                    f"[{cls.TAG}] analyze start path={cls.codebase_path()} "
                    f"target={target} symbol_summary={cls.ENABLE_SYMBOL_SUMMARY} "
                    f"clear={need_clear}",
                    flush=True,
                )
                await FileAnalysisService.stop_global_scheduler()
                try:
                    await AnalysisService.stop_scan(repo_id, reason=f"{cls.TAG} reset")
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
                print(
                    f"[{cls.TAG}] analyze done completed={a.get('completed_files')} "
                    f"failed={a.get('failed_files')} embedded={a.get('embedded_files')} "
                    f"searchable={a.get('searchable_files')}",
                    flush=True,
                )
                cls._vector_ready = True
            return repo_id
