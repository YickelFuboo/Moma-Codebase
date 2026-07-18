"""清库重建被测仓 app/：先停调度、清掉两仓脏 pending，再串行重建并评测。"""
from __future__ import annotations
import os
import sys
import traceback


PANDO_ID = "c2664c22-3eaa-45eb-b950-d3596667d4c7"
KB_ID = "61b6ba68-b25c-40ef-af24-125386cfb497"


async def _purge_outside_app(repo_id: str) -> int:
    """删除非 app/ 下的文件分析状态，避免调度器继续啃 参考项目 等脏数据。"""
    from sqlalchemy import delete
    from app.infrastructure.database import get_db_session
    from app.repo_analysis.models.analysis_status import RepoFileAnalysisState

    async with get_db_session() as db:
        rows = await db.execute(
            delete(RepoFileAnalysisState).where(
                RepoFileAnalysisState.repo_id == repo_id,
                RepoFileAnalysisState.file_path.notlike("app/%"),
            )
        )
        await db.commit()
        return int(rows.rowcount or 0)


async def _preflight() -> None:
    from app.runtime import init_runtime
    from app.repo_analysis.services.analysis_service import AnalysisService
    from app.repo_analysis.services.file_analysis_service import FileAnalysisService

    await init_runtime()
    await FileAnalysisService.stop_global_scheduler()
    for rid in (PANDO_ID, KB_ID):
        try:
            await AnalysisService.stop_scan(rid, reason="preflight")
        except Exception:
            pass
        await FileAnalysisService.stop_analysis(rid)
        n = await _purge_outside_app(rid)
        print(f"[preflight] purge outside app/ repo={rid} deleted={n}", flush=True)


def _run_rebuild(session_cls, label: str, clear_env: str) -> dict:
    os.environ[clear_env] = "1"
    # 避免另一仓 clear 污染本轮
    other = "PANDO_CLEAR" if clear_env == "KB_CLEAR" else "KB_CLEAR"
    os.environ.pop(other, None)

    session_cls._vector_ready = False
    if hasattr(session_cls, "_graph_ready"):
        session_cls._graph_ready = False
    session_cls._session_repo_id = None
    session_cls._session_repo_path = None

    async def _one():
        from app.repo_analysis.services.analysis_service import AnalysisService
        from app.repo_analysis.services.file_analysis_service import FileAnalysisService

        await FileAnalysisService.stop_global_scheduler()
        for rid in (PANDO_ID, KB_ID):
            await FileAnalysisService.stop_analysis(rid)
            n = await _purge_outside_app(rid)
            if n:
                print(f"[rebuild] purge {rid} outside app deleted={n}", flush=True)

        repo_id = await session_cls.ensure_vector_ready()
        n = await _purge_outside_app(repo_id)
        if n:
            print(f"[rebuild] post-purge {label} deleted={n}", flush=True)
        summary = await AnalysisService.get_summary(repo_id)
        a = summary.get("analysis_summary") or {}
        return {
            "label": label,
            "repo_id": repo_id,
            "path": str(session_cls.codebase_path()),
            "completed": int(a.get("completed_files") or 0),
            "failed": int(a.get("failed_files") or 0),
            "pending": int(a.get("pending_files") or 0),
            "running": int(a.get("running_files") or 0),
        }

    print(f"\n===== rebuild {label} clear={clear_env}=1 =====", flush=True)
    info = session_cls.run_async(_one())
    print(f"[rebuild-done] {info}", flush=True)
    return info


def _run_pytest(args: list[str]) -> int:
    import pytest

    print(f"\n===== pytest {' '.join(args)} =====", flush=True)
    os.environ.pop("PANDO_CLEAR", None)
    os.environ.pop("KB_CLEAR", None)
    return int(pytest.main(args))


def main() -> int:
    # 重建期间禁止增量全仓扫，否则会把 参考项目 等脏路径再次登记进 pending
    os.environ["ENABLE_INCREMENTAL_SCAN"] = "false"

    from app.config.settings import settings
    from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession
    from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession

    settings.enable_incremental_scan = False
    KnowledgeBaseScenarioSession.run_async(_preflight())

    results = []
    try:
        results.append(_run_rebuild(KnowledgeBaseScenarioSession, "KnowledegBase-Service", "KB_CLEAR"))
        results.append(_run_rebuild(PandoAgentScenarioSession, "Pando-Agent", "PANDO_CLEAR"))
    except Exception:
        traceback.print_exc()
        return 2

    bad = [r for r in results if r.get("failed", 0) > 0 or r.get("completed", 0) <= 0]
    if bad:
        print(f"[rebuild] FAILED summaries={bad}", flush=True)
        return 3

    code = 0
    code |= _run_pytest(
        [
            "tests/scenarios/pando_agent/test_similar_accuracy.py",
            "tests/scenarios/knowledge_base/test_similar_accuracy.py",
            "-q",
            "--tb=line",
            "-s",
        ]
    )
    code |= _run_pytest(
        [
            "tests/scenarios/pando_agent/test_related_hybrid_accuracy.py",
            "tests/scenarios/knowledge_base/test_related_accuracy.py",
            "-q",
            "--tb=line",
            "-s",
        ]
    )
    print(f"\n[all-done] rebuild={results} pytest_exit={code}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
