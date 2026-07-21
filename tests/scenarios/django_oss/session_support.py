"""开源大仓 Django：scenario 会话。

分析范围：整个 django/ 包（含 db / http / contrib / middleware / urls / core 等多子目录）。
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import pytest
from tests.scenarios.base import CodebaseScenarioBase


DEFAULT_DJANGO_PATH = Path(r"F:\开源项目\django")


class DjangoOssScenarioSession(CodebaseScenarioBase):
    """登记并分析 Django 源码包（默认 D：符号摘要 ON）。"""

    ENABLE_SYMBOL_SUMMARY = True
    ENABLE_CODE_GRAPH = False
    # 整包：覆盖 db / http / contrib / middleware / urls / forms / views / core 等
    ANALYZE_TARGET = "django"
    CLEAR_BEFORE_ANALYZE = False
    ANALYZE_TIMEOUT_SEC = 18000
    POLL_INTERVAL_SEC = 8
    FILE_WORKER_COUNT = 6
    EXTRA_EXCLUDED_DIRS = {
        "tests",
        "docs",
        "js_tests",
        "node_modules",
        ".venv",
        ".tox",
        "__pycache__",
        "locale",
        "migrations",
    }

    _loop = None
    _vector_ready: bool = False
    _session_repo_id = None
    _session_repo_path = None

    @classmethod
    def _should_clear(cls) -> bool:
        return os.environ.get("DJANGO_CLEAR", "").strip() in {"1", "true", "True"}

    @classmethod
    def apply_feature_flags(cls) -> None:
        super().apply_feature_flags()
        from app.repo_analysis.services.analysis_service import AnalysisService

        AnalysisService.EXCLUDED_DIRS = set(AnalysisService.EXCLUDED_DIRS) | set(cls.EXTRA_EXCLUDED_DIRS)

    @classmethod
    def codebase_path(cls) -> Path:
        raw = (os.environ.get("DJANGO_OSS_PATH") or "").strip()
        if raw:
            return Path(raw).resolve()
        return DEFAULT_DJANGO_PATH.resolve()

    @classmethod
    def require_repo_or_skip(cls) -> Path:
        path = cls.codebase_path()
        if not path.is_dir():
            pytest.skip(f"Django 仓不存在: {path}")
        pkg = path / "django"
        if not pkg.is_dir():
            pytest.skip(f"缺少 django/ 包目录: {path}")
        for sub in ("db", "http", "contrib"):
            if not (pkg / sub).is_dir():
                pytest.skip(f"缺少 django/{sub}: {path}")
        return path

    @classmethod
    def run_async(cls, coro):
        if DjangoOssScenarioSession._loop is None or DjangoOssScenarioSession._loop.is_closed():
            DjangoOssScenarioSession._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(DjangoOssScenarioSession._loop)
        return DjangoOssScenarioSession._loop.run_until_complete(coro)

    @classmethod
    def _async_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = getattr(DjangoOssScenarioSession, "_lock", None)
        if lock is None or getattr(DjangoOssScenarioSession, "_lock_loop_id", None) != id(loop):
            DjangoOssScenarioSession._lock = asyncio.Lock()
            DjangoOssScenarioSession._lock_loop_id = id(loop)
        return DjangoOssScenarioSession._lock

    @classmethod
    async def ensure_repo(cls) -> str:
        cls.require_repo_or_skip()
        if DjangoOssScenarioSession._session_repo_id and DjangoOssScenarioSession._session_repo_path:
            cls.apply_feature_flags()
            import app.runtime as runtime_mod
            if not getattr(runtime_mod, "_runtime_inited", False):
                await cls._reset_runtime()
            cls._repo_id = DjangoOssScenarioSession._session_repo_id
            cls._repo_path = DjangoOssScenarioSession._session_repo_path
            return DjangoOssScenarioSession._session_repo_id
        repo_id = await super().ensure_repo()
        DjangoOssScenarioSession._session_repo_id = repo_id
        DjangoOssScenarioSession._session_repo_path = cls._repo_path
        return repo_id

    @classmethod
    async def ensure_vector_ready(cls) -> str:
        async with cls._async_lock():
            need_clear = bool(cls._should_clear() or cls.CLEAR_BEFORE_ANALYZE) and not DjangoOssScenarioSession._vector_ready
            repo_id = await cls.ensure_repo()
            if not DjangoOssScenarioSession._vector_ready:
                from app.repo_analysis.services.analysis_service import AnalysisService
                from app.repo_analysis.services.file_analysis_service import FileAnalysisService

                print(
                    f"[django-oss] analyze start path={cls.codebase_path()} "
                    f"target={cls.ANALYZE_TARGET} (db/http/contrib/...) "
                    f"symbol_summary={cls.ENABLE_SYMBOL_SUMMARY} clear={need_clear}",
                    flush=True,
                )
                await FileAnalysisService.stop_global_scheduler()
                try:
                    await AnalysisService.stop_scan(repo_id, reason="django oss reset")
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
                    f"[django-oss] analyze done completed={a.get('completed_files')} "
                    f"failed={a.get('failed_files')} embedded={a.get('embedded_files')}",
                    flush=True,
                )
                DjangoOssScenarioSession._vector_ready = True
            return repo_id
