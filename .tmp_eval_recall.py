"""清理卡住状态后：KB 沿用已完成索引；Pando 仅重建 app/；再跑召回评测。"""
from __future__ import annotations
import os
import sys
import traceback


PANDO_ID = "c2664c22-3eaa-45eb-b950-d3596667d4c7"
KB_ID = "61b6ba68-b25c-40ef-af24-125386cfb497"


async def _preflight() -> None:
    from datetime import datetime
    from sqlalchemy import delete, update
    from app.runtime import init_runtime
    from app.config.settings import settings
    from app.infrastructure.database import get_db_session
    from app.repo_analysis.models.analysis_status import FileAnalysisStatus, RepoFileAnalysisState
    from app.repo_analysis.services.analysis_service import AnalysisService
    from app.repo_analysis.services.file_analysis_service import FileAnalysisService

    settings.enable_incremental_scan = False
    os.environ["ENABLE_INCREMENTAL_SCAN"] = "false"
    await init_runtime()
    await FileAnalysisService.stop_global_scheduler()
    for rid in (PANDO_ID, KB_ID):
        try:
            await AnalysisService.stop_scan(rid, reason="eval preflight")
        except Exception:
            pass
        await FileAnalysisService.stop_analysis(rid)

    async with get_db_session() as db:
        # 卡住的 RUNNING 复位为 pending，避免场景轮询永远不结束
        await db.execute(
            update(RepoFileAnalysisState)
            .where(RepoFileAnalysisState.status == FileAnalysisStatus.RUNNING.value)
            .values(
                status=FileAnalysisStatus.PENDING.value,
                last_error="reset stuck running for eval",
                updated_at=datetime.now(),
            )
        )
        # Pando 非 app/ 全删
        r = await db.execute(
            delete(RepoFileAnalysisState).where(
                RepoFileAnalysisState.repo_id == PANDO_ID,
                RepoFileAnalysisState.file_path.notlike("app/%"),
            )
        )
        await db.commit()
        print(f"[preflight] purged pando outside app={int(r.rowcount or 0)}", flush=True)


def _mark_kb_ready() -> None:
    from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession

    async def _one():
        repo_id = await KnowledgeBaseScenarioSession.ensure_repo()
        from app.repo_analysis.services.analysis_service import AnalysisService
        from app.repo_analysis.services.file_analysis_service import FileAnalysisService

        FileAnalysisService.start_global_scheduler(
            interval_seconds=2.0,
            worker_count=KnowledgeBaseScenarioSession.FILE_WORKER_COUNT,
        )
        # 消化残留 pending（若有），但不 clear
        os.environ.pop("KB_CLEAR", None)
        KnowledgeBaseScenarioSession.CLEAR_BEFORE_ANALYZE = False
        KnowledgeBaseScenarioSession._vector_ready = False
        summary = await KnowledgeBaseScenarioSession.run_analyze()
        a = summary.get("analysis_summary") or {}
        KnowledgeBaseScenarioSession._vector_ready = True
        KnowledgeBaseScenarioSession._session_repo_id = repo_id
        KnowledgeBaseScenarioSession._session_repo_path = KnowledgeBaseScenarioSession._repo_path
        print(f"[kb-ready] {a}", flush=True)
        return a

    return KnowledgeBaseScenarioSession.run_async(_one())


def _rebuild_pando() -> dict:
    from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession

    os.environ["PANDO_CLEAR"] = "1"
    os.environ.pop("KB_CLEAR", None)
    PandoAgentScenarioSession._vector_ready = False
    PandoAgentScenarioSession._graph_ready = False
    PandoAgentScenarioSession._session_repo_id = None
    PandoAgentScenarioSession._session_repo_path = None

    async def _one():
        from app.repo_analysis.services.analysis_service import AnalysisService

        repo_id = await PandoAgentScenarioSession.ensure_vector_ready()
        summary = await AnalysisService.get_summary(repo_id)
        a = summary.get("analysis_summary") or {}
        info = {
            "completed": int(a.get("completed_files") or 0),
            "failed": int(a.get("failed_files") or 0),
            "pending": int(a.get("pending_files") or 0),
            "running": int(a.get("running_files") or 0),
        }
        print(f"[pando-ready] {info}", flush=True)
        return info

    return PandoAgentScenarioSession.run_async(_one())


def _run_pytest(args: list[str]) -> int:
    import pytest

    os.environ.pop("PANDO_CLEAR", None)
    os.environ.pop("KB_CLEAR", None)
    print(f"\n===== pytest {' '.join(args)} =====", flush=True)
    return int(pytest.main(args))


def main() -> int:
    os.environ["ENABLE_INCREMENTAL_SCAN"] = "false"
    from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession
    from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession

    KnowledgeBaseScenarioSession.run_async(_preflight())
    try:
        _mark_kb_ready()
        # 避免调度器绑在 KB 的 event loop 上，切到 Pando 前先关干净
        KnowledgeBaseScenarioSession.run_async(KnowledgeBaseScenarioSession.shutdown_runtime())
        pando = _rebuild_pando()
        if pando.get("failed", 0) > 0 or pando.get("completed", 0) <= 0:
            print(f"[eval] pando rebuild bad: {pando}", flush=True)
            return 3
    except Exception:
        traceback.print_exc()
        return 2

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
    print(f"\n[all-done] pytest_exit={code}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
