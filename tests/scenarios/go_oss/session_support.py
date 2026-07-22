"""开源大仓 Go：scenario 会话。

分析范围：src 下 net / encoding / context 三包（全量 src ~5900 文件 + 符号摘要约需数日，已停用）。
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import pytest
from tests.scenarios.base import CodebaseScenarioBase


DEFAULT_GO_PATH = Path(r"F:\开源项目\go")

_GO_SRC_ALLOW = {"net", "encoding", "context"}
_GO_SRC_ALL = {
    "archive", "arena", "bufio", "builtin", "bytes", "cmd", "cmp", "compress",
    "container", "context", "crypto", "database", "debug", "embed", "encoding",
    "errors", "expvar", "flag", "fmt", "go", "hash", "html", "image", "index",
    "internal", "io", "iter", "log", "maps", "math", "mime", "net", "os", "path",
    "plugin", "reflect", "regexp", "runtime", "simd", "slices", "sort", "strconv",
    "strings", "structs", "sync", "syscall", "testdata", "testing", "text", "time",
    "unicode", "unique", "unsafe", "uuid", "vendor", "weak",
}


class GoOssScenarioSession(CodebaseScenarioBase):
    """登记并分析 Go 标准库三包子集（默认 D：符号摘要 ON）。"""

    ENABLE_SYMBOL_SUMMARY = True
    ENABLE_CODE_GRAPH = False
    ANALYZE_TARGET = "src"
    CLEAR_BEFORE_ANALYZE = False
    ANALYZE_TIMEOUT_SEC = 14400
    POLL_INTERVAL_SEC = 8
    FILE_WORKER_COUNT = 6
    EXTRA_EXCLUDED_DIRS = (_GO_SRC_ALL - _GO_SRC_ALLOW) | {
        "testdata",
        "node_modules",
        ".git",
        "vendor",
    }

    _loop = None
    _vector_ready: bool = False
    _session_repo_id = None
    _session_repo_path = None

    @classmethod
    def _should_clear(cls) -> bool:
        return os.environ.get("GO_CLEAR", "").strip() in {"1", "true", "True"}

    @classmethod
    def apply_feature_flags(cls) -> None:
        super().apply_feature_flags()
        from app.repo_analysis.services.analysis_service import AnalysisService

        AnalysisService.EXCLUDED_DIRS = set(AnalysisService.EXCLUDED_DIRS) | set(cls.EXTRA_EXCLUDED_DIRS)

    @classmethod
    def codebase_path(cls) -> Path:
        raw = (os.environ.get("GO_OSS_PATH") or "").strip()
        if raw:
            return Path(raw).resolve()
        return DEFAULT_GO_PATH.resolve()

    @classmethod
    def require_repo_or_skip(cls) -> Path:
        path = cls.codebase_path()
        if not path.is_dir():
            pytest.skip(f"Go 仓不存在: {path}")
        for pkg in _GO_SRC_ALLOW:
            if not (path / "src" / pkg).is_dir():
                pytest.skip(f"缺少 src/{pkg}: {path}")
        return path

    @classmethod
    def run_async(cls, coro):
        if GoOssScenarioSession._loop is None or GoOssScenarioSession._loop.is_closed():
            GoOssScenarioSession._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(GoOssScenarioSession._loop)
        return GoOssScenarioSession._loop.run_until_complete(coro)

    @classmethod
    def _async_lock(cls) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = getattr(GoOssScenarioSession, "_lock", None)
        if lock is None or getattr(GoOssScenarioSession, "_lock_loop_id", None) != id(loop):
            GoOssScenarioSession._lock = asyncio.Lock()
            GoOssScenarioSession._lock_loop_id = id(loop)
        return GoOssScenarioSession._lock

    @classmethod
    async def ensure_repo(cls) -> str:
        cls.require_repo_or_skip()
        if GoOssScenarioSession._session_repo_id and GoOssScenarioSession._session_repo_path:
            cls.apply_feature_flags()
            import app.runtime as runtime_mod
            if not getattr(runtime_mod, "_runtime_inited", False):
                await cls._reset_runtime()
            cls._repo_id = GoOssScenarioSession._session_repo_id
            cls._repo_path = GoOssScenarioSession._session_repo_path
            return GoOssScenarioSession._session_repo_id
        repo_id = await super().ensure_repo()
        GoOssScenarioSession._session_repo_id = repo_id
        GoOssScenarioSession._session_repo_path = cls._repo_path
        return repo_id

    @classmethod
    async def ensure_vector_ready(cls) -> str:
        async with cls._async_lock():
            need_clear = bool(cls._should_clear() or cls.CLEAR_BEFORE_ANALYZE) and not GoOssScenarioSession._vector_ready
            repo_id = await cls.ensure_repo()
            if not GoOssScenarioSession._vector_ready:
                from app.repo_analysis.services.analysis_service import AnalysisService
                from app.repo_analysis.services.file_analysis_service import FileAnalysisService

                print(
                    f"[go-oss] analyze start path={cls.codebase_path()} "
                    f"target={cls.ANALYZE_TARGET} allow={sorted(_GO_SRC_ALLOW)} "
                    f"symbol_summary={cls.ENABLE_SYMBOL_SUMMARY} clear={need_clear}",
                    flush=True,
                )
                await FileAnalysisService.stop_global_scheduler()
                try:
                    await AnalysisService.stop_scan(repo_id, reason="go oss reset")
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
                    f"[go-oss] analyze done completed={a.get('completed_files')} "
                    f"failed={a.get('failed_files')} embedded={a.get('embedded_files')}",
                    flush=True,
                )
                GoOssScenarioSession._vector_ready = True
            return repo_id
