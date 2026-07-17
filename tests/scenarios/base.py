"""本仓场景回归测试基类。

约定：
- 代码仓路径固定为本仓库根目录
- 一场景一用例类，继承本基类后实现 test_scenario
- 子类通过类属性开关功能；后续改动可继续继承做回归断言
"""
from __future__ import annotations
import asyncio
import json
import os
import time
from abc import ABC
from pathlib import Path
from typing import Any, Dict, List, Optional


# 写死为本项目根目录（tests/scenarios -> 上两级）
CODEBASE_PATH = Path(__file__).resolve().parents[2]


class CodebaseScenarioBase(ABC):
    """场景基类：登记本仓、按开关分析、提供检索与断言辅助。"""

    # --- 场景开关（子类覆盖）---
    ENABLE_SYMBOL_SUMMARY: bool = False
    ENABLE_CODE_GRAPH: bool = True
    CODE_GRAPH_PROVIDER: str = "codegraph"
    ANALYZE_TARGET: str = "app/repo_analysis/services/codegraph"
    CLEAR_BEFORE_ANALYZE: bool = True
    ANALYZE_TIMEOUT_SEC: int = 900
    POLL_INTERVAL_SEC: int = 5

    # 期望命中的本仓路径片段（子类可覆盖）
    EXPECT_PATH_FRAGMENTS: List[str] = [
        "app/repo_analysis/services/codegraph",
    ]

    _repo_id: Optional[str] = None
    _repo_path: Optional[str] = None

    @classmethod
    def codebase_path(cls) -> Path:
        return CODEBASE_PATH

    @classmethod
    def apply_feature_flags(cls) -> None:
        from app.config.settings import settings

        settings.code_graph_enabled = bool(cls.ENABLE_CODE_GRAPH)
        settings.code_graph_provider = cls.CODE_GRAPH_PROVIDER
        settings.code_analysis_symbol_summary_enabled = bool(cls.ENABLE_SYMBOL_SUMMARY)
        settings.code_analysis_line_chunk_enabled = True
        settings.mr_experience_enabled = True
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
        CodeGraphGateway.reset_provider()

    @classmethod
    async def _reset_runtime(cls) -> None:
        import app.runtime as runtime_mod
        from app.infrastructure.database import factory as db_factory_mod

        runtime_mod._runtime_inited = False
        runtime_mod._schema_migrated = False
        db_factory_mod._database_factory._connection = None
        from app.runtime import init_runtime, ensure_scheduler
        await init_runtime()
        await ensure_scheduler()

    @classmethod
    async def ensure_repo(cls) -> str:
        from app.cli.common import DEFAULT_USER_ID, default_repo_name
        from app.infrastructure.database import get_db_session
        from app.repo_mgmt.models.git_repo_mgmt import RepoKind
        from app.repo_mgmt.services.git_repo_service import GitRepositoryService
        from app.repo_mgmt.services.repo_resolver import RepoResolver

        cls.apply_feature_flags()
        await cls._reset_runtime()
        normalized = RepoResolver.normalize_repo_path(str(cls.codebase_path()))
        cls._repo_path = normalized
        async with get_db_session() as db:
            repo = await RepoResolver.get_by_path(db, normalized)
            if not repo:
                repo = await GitRepositoryService.create_repository_from_path(
                    session=db,
                    user_id=DEFAULT_USER_ID,
                    name=default_repo_name(normalized),
                    description="scenario-regression",
                    local_repo_path=normalized,
                    git_url="",
                    kind=RepoKind.CODE,
                )
            else:
                await db.refresh(repo)
                db.expunge(repo)
            cls._repo_id = repo.id
            return repo.id

    @classmethod
    async def run_analyze(cls) -> Dict[str, Any]:
        from app.repo_analysis.models.analysis_status import FileAnalysisStatus, RepoAnalysisStatus
        from app.repo_analysis.services.analysis_service import AnalysisService

        repo_id = cls._repo_id or await cls.ensure_repo()
        if cls.CLEAR_BEFORE_ANALYZE:
            await AnalysisService.delete_repo_analysis_data(repo_id)
        start = await AnalysisService.start_scan(
            repo_id=repo_id,
            target_rel_path=cls.ANALYZE_TARGET,
        )
        deadline = time.time() + cls.ANALYZE_TIMEOUT_SEC
        last: Dict[str, Any] = {}
        stable = 0
        while time.time() < deadline:
            summary = await AnalysisService.get_summary(repo_id)
            last = summary
            scan = (summary.get("scan") or {})
            scan_status = scan.get("scan_status")
            a = summary.get("analysis_summary") or {}
            pending = int(a.get("pending_files") or 0)
            running = int(a.get("running_files") or 0)
            completed = int(a.get("completed_files") or 0)
            failed = int(a.get("failed_files") or 0)
            skipped = int(a.get("skipped_files") or 0)
            in_mem = bool(a.get("scan_active_in_process"))
            scan_done = scan_status in (
                RepoAnalysisStatus.COMPLETED.value,
                RepoAnalysisStatus.FAILED.value,
                RepoAnalysisStatus.IDLE.value,
            ) and not in_mem
            if scan_done and pending == 0 and running == 0 and (completed + failed + skipped) > 0:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            print(
                f"[scenario] analyze poll status={scan_status} "
                f"completed={completed} pending={pending} running={running} failed={failed}",
                flush=True,
            )
            await asyncio.sleep(cls.POLL_INTERVAL_SEC)
        a = (last.get("analysis_summary") or {})
        if int(a.get("completed_files") or 0) <= 0:
            raise AssertionError(f"分析未产生完成文件: {json.dumps(last, ensure_ascii=False, default=str)}")
        return last

    @classmethod
    async def search_similar(cls, code: str, top_k: int = 8) -> Dict[str, Any]:
        from app.repo_analysis.services.search_service import SearchService
        repo_id = cls._repo_id or await cls.ensure_repo()
        return await SearchService.search_similar_code(repo_id, code, top_k=top_k)

    @classmethod
    async def search_related(cls, keywords: List[str], top_k: int = 8) -> Dict[str, Any]:
        from app.repo_analysis.services.search_service import SearchService
        repo_id = cls._repo_id or await cls.ensure_repo()
        return await SearchService.search_related_files(repo_id, keywords, top_k=top_k)

    @staticmethod
    def assert_has_hits(result: Dict[str, Any], min_total: int = 1) -> None:
        total = int(result.get("total") or 0)
        assert total >= min_total, f"期望至少 {min_total} 条命中，实际={total}, result={result}"

    @classmethod
    def assert_paths_match_expected(cls, result: Dict[str, Any]) -> None:
        items = result.get("items") or []
        paths = [str(it.get("file_path") or "") for it in items]
        assert paths, f"无命中路径: {result}"
        joined = "\n".join(paths)
        matched = [frag for frag in cls.EXPECT_PATH_FRAGMENTS if frag.replace("\\", "/") in joined.replace("\\", "/")]
        assert matched, (
            f"命中路径未覆盖期望片段 {cls.EXPECT_PATH_FRAGMENTS}；实际 paths={paths}"
        )

    @classmethod
    async def shutdown_runtime(cls) -> None:
        from app.runtime import shutdown
        await shutdown()

    def run_async(self, coro):
        return asyncio.run(coro)
