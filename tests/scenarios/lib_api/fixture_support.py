"""迷你 Lib 夹具与会话：用于 Lib 功能/场景测试。"""
from __future__ import annotations
import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Optional


class MiniLibFixture:
    """在临时目录生成含 Py/Go/Java 公开接口的迷你库。"""

    def __init__(self) -> None:
        self.root: Optional[Path] = None

    def create(self) -> Path:
        self.root = Path(tempfile.mkdtemp(prefix="moma_mini_lib_"))
        py = self.root / "io_api.py"
        py.write_text(
            '"""文件读写公共库"""\n'
            "\n"
            "def read_text(path: str) -> str:\n"
            '    """读取文本文件全部内容并返回字符串。"""\n'
            "    with open(path, encoding='utf-8') as f:\n"
            "        return f.read()\n"
            "\n"
            "def write_text(path: str, content: str) -> None:\n"
            '    """将字符串写入文本文件。"""\n'
            "    with open(path, 'w', encoding='utf-8') as f:\n"
            "        f.write(content)\n"
            "\n"
            "def _internal_helper():\n"
            "    return True\n",
            encoding="utf-8",
        )
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_io.py").write_text(
            "def test_dummy():\n    assert True\n",
            encoding="utf-8",
        )
        go = self.root / "hashutil.go"
        go.write_text(
            "package hashutil\n\n"
            "// Digest 计算输入字符串的摘要标识。\n"
            "func Digest(s string) string {\n"
            '    return "d:" + s\n'
            "}\n\n"
            "func hidden() string {\n"
            '    return "x"\n'
            "}\n",
            encoding="utf-8",
        )
        java = self.root / "JsonHelper.java"
        java.write_text(
            "public class JsonHelper {\n"
            "    /** 将对象序列化为 JSON 文本。 */\n"
            "    public String toJson(Object value) {\n"
            '        return String.valueOf(value);\n'
            "    }\n"
            "    private String secret() {\n"
            '        return "no";\n'
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        return self.root

    def cleanup(self) -> None:
        if self.root and self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root = None


class LibScenarioSession:
    """独立 Lib 场景会话（不与 code 场景共享仓库）。"""

    _loop = None
    _repo_id: Optional[str] = None
    _repo_path: Optional[str] = None

    @classmethod
    def run_async(cls, coro):
        if cls._loop is None or cls._loop.is_closed():
            cls._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(cls._loop)
        return cls._loop.run_until_complete(coro)

    @classmethod
    async def reset_runtime(cls) -> None:
        import app.runtime as runtime_mod
        from app.infrastructure.database import factory as db_factory_mod

        runtime_mod._runtime_inited = False
        runtime_mod._schema_migrated = False
        db_factory_mod._database_factory._connection = None
        from app.runtime import init_runtime, ensure_scheduler

        await init_runtime()
        await ensure_scheduler()

    @classmethod
    async def register_lib(cls, lib_path: Path) -> str:
        from app.cli.common import DEFAULT_USER_ID, default_repo_name
        from app.config.settings import settings
        from app.infrastructure.database import get_db_session
        from app.repo_mgmt.models.git_repo_mgmt import RepoKind
        from app.repo_mgmt.services.git_repo_service import GitRepositoryService
        from app.repo_mgmt.services.repo_resolver import RepoResolver

        settings.code_graph_enabled = False
        await cls.reset_runtime()
        normalized = RepoResolver.normalize_repo_path(str(lib_path))
        cls._repo_path = normalized
        async with get_db_session() as db:
            existing = await RepoResolver.get_by_path(db, normalized)
            if existing:
                await GitRepositoryService.delete_repository(
                    db, existing.id, DEFAULT_USER_ID, delete_local=False
                )
            repo = await GitRepositoryService.create_repository_from_path(
                session=db,
                user_id=DEFAULT_USER_ID,
                name=default_repo_name(normalized),
                description="lib-scenario",
                local_repo_path=normalized,
                git_url="",
                kind=RepoKind.LIB,
            )
            cls._repo_id = repo.id
            return repo.id

    @classmethod
    async def analyze_and_wait(cls, timeout_sec: int = 180) -> None:
        import time
        from app.lib_analysis.services.analysis_service import LibAnalysisService
        from app.repo_analysis.models.analysis_status import FileAnalysisStatus, RepoAnalysisStatus
        from app.repo_analysis.services.file_analysis_service import FileAnalysisService
        from app.infrastructure.database import get_db_session
        from sqlalchemy import func, select
        from app.repo_analysis.models.analysis_status import RepoFileAnalysisState

        assert cls._repo_id
        await FileAnalysisService.stop_global_scheduler()
        await LibAnalysisService.delete_repo_analysis_data(cls._repo_id)
        FileAnalysisService.start_global_scheduler(interval_seconds=1.0, worker_count=2)
        await LibAnalysisService.start_scan(cls._repo_id)

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            async with get_db_session() as db:
                pending = await db.scalar(
                    select(func.count())
                    .select_from(RepoFileAnalysisState)
                    .where(
                        RepoFileAnalysisState.repo_id == cls._repo_id,
                        RepoFileAnalysisState.status.in_(
                            [
                                FileAnalysisStatus.PENDING.value,
                                FileAnalysisStatus.RUNNING.value,
                                FileAnalysisStatus.FAILED.value,
                            ]
                        ),
                    )
                )
                summary = await LibAnalysisService.get_summary(cls._repo_id)
            scan = summary.get("scan_status")
            if scan == RepoAnalysisStatus.COMPLETED.value and int(pending or 0) == 0:
                return
            if scan == RepoAnalysisStatus.FAILED.value:
                raise RuntimeError(f"lib scan failed: {summary}")
            await asyncio.sleep(1.5)
        raise TimeoutError("lib analyze timeout")

    @classmethod
    async def shutdown(cls) -> None:
        from app.repo_analysis.services.file_analysis_service import FileAnalysisService
        from app.runtime import shutdown_runtime

        try:
            await FileAnalysisService.stop_global_scheduler()
        except Exception:
            pass
        try:
            await shutdown_runtime()
        except Exception:
            pass
        cls._repo_id = None
        cls._repo_path = None
        if cls._loop is not None and not cls._loop.is_closed():
            cls._loop.close()
        cls._loop = None
