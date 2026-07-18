"""仅重建 Pando app/（KB 已就绪），再跑两边召回评测。"""
from __future__ import annotations
import os
import sys
import traceback


PANDO_ID = "c2664c22-3eaa-45eb-b950-d3596667d4c7"


async def _preflight() -> None:
    from sqlalchemy import delete
    from app.runtime import init_runtime
    from app.config.settings import settings
    from app.infrastructure.database import get_db_session
    from app.repo_analysis.models.analysis_status import RepoFileAnalysisState
    from app.repo_analysis.services.analysis_service import AnalysisService
    from app.repo_analysis.services.file_analysis_service import FileAnalysisService

    settings.enable_incremental_scan = False
    os.environ["ENABLE_INCREMENTAL_SCAN"] = "false"
    await init_runtime()
    await FileAnalysisService.stop_global_scheduler()
    try:
        await AnalysisService.stop_scan(PANDO_ID, reason="eval preflight")
    except Exception:
        pass
    await FileAnalysisService.stop_analysis(PANDO_ID)
    async with get_db_session() as db:
        r = await db.execute(
            delete(RepoFileAnalysisState).where(
                RepoFileAnalysisState.repo_id == PANDO_ID,
                RepoFileAnalysisState.file_path.notlike("app/%"),
            )
        )
        await db.commit()
        print(f"[preflight] purged pando outside app={int(r.rowcount or 0)}", flush=True)


def main() -> int:
    os.environ["ENABLE_INCREMENTAL_SCAN"] = "false"
    os.environ["PANDO_CLEAR"] = "1"
    os.environ.pop("KB_CLEAR", None)

    from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession
    from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession
    import pytest

    PandoAgentScenarioSession.run_async(_preflight())
    PandoAgentScenarioSession._vector_ready = False
    PandoAgentScenarioSession._graph_ready = False
    PandoAgentScenarioSession._session_repo_id = None
    PandoAgentScenarioSession._session_repo_path = None

    try:
        async def _rebuild():
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

        info = PandoAgentScenarioSession.run_async(_rebuild())
        if info.get("failed", 0) > 0 or info.get("completed", 0) <= 0:
            print(f"[eval] pando bad {info}", flush=True)
            return 3
    except Exception:
        traceback.print_exc()
        return 2

    os.environ.pop("PANDO_CLEAR", None)
    # KB 已有索引，评测不清库
    KnowledgeBaseScenarioSession._vector_ready = True
    code = 0
    code |= int(
        pytest.main(
            [
                "tests/scenarios/pando_agent/test_similar_accuracy.py",
                "tests/scenarios/knowledge_base/test_similar_accuracy.py",
                "-q",
                "--tb=line",
                "-s",
            ]
        )
    )
    code |= int(
        pytest.main(
            [
                "tests/scenarios/pando_agent/test_related_hybrid_accuracy.py",
                "tests/scenarios/knowledge_base/test_related_accuracy.py",
                "-q",
                "--tb=line",
                "-s",
            ]
        )
    )
    print(f"\n[all-done] pytest_exit={code}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
