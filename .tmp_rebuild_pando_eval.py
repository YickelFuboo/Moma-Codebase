"""Pando app/ 干净重建索引（drop 向量表）后跑 similar + related 评测。"""
from __future__ import annotations
import os
import sys
import traceback


PANDO_ID = "c2664c22-3eaa-45eb-b950-d3596667d4c7"


async def _force_drop_pando_spaces() -> None:
    from app.infrastructure.vector_store import VECTOR_STORE_CONN
    from app.repo_analysis.constants import line_chunk_space_name, symbol_summary_space_name

    dim = 1024
    for space in (
        line_chunk_space_name(PANDO_ID, dim),
        symbol_summary_space_name(PANDO_ID, dim),
    ):
        ok = await VECTOR_STORE_CONN.delete_space(space)
        print(f"[preflight] delete_space {space} ok={ok}", flush=True)


async def _preflight() -> None:
    from sqlalchemy import delete, update
    from app.runtime import init_runtime
    from app.config.settings import settings
    from app.infrastructure.database import get_db_session
    from app.repo_analysis.models.analysis_status import (
        FileAnalysisStatus,
        RepoFileAnalysisState,
    )
    from app.repo_analysis.services.analysis_service import AnalysisService
    from app.repo_analysis.services.file_analysis_service import FileAnalysisService

    settings.enable_incremental_scan = False
    os.environ["ENABLE_INCREMENTAL_SCAN"] = "false"
    await init_runtime()
    await FileAnalysisService.stop_global_scheduler()
    try:
        await AnalysisService.stop_scan(PANDO_ID, reason="pando rebuild preflight")
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
        # 卡住的 RUNNING 先打回，避免 poll 永远不结束
        await db.execute(
            update(RepoFileAnalysisState)
            .where(
                RepoFileAnalysisState.repo_id == PANDO_ID,
                RepoFileAnalysisState.status == FileAnalysisStatus.RUNNING.value,
            )
            .values(status=FileAnalysisStatus.PENDING.value, last_error="rebuild reset")
        )
        await db.commit()
        print(f"[preflight] purged pando outside app={int(r.rowcount or 0)}", flush=True)

    await _force_drop_pando_spaces()


async def _postcheck(repo_id: str) -> dict:
    from app.infrastructure.vector_store import VECTOR_STORE_CONN
    from app.repo_analysis.constants import line_chunk_space_name, symbol_summary_space_name
    from app.repo_analysis.services.analysis_service import AnalysisService

    dim = 1024
    ss = symbol_summary_space_name(repo_id, dim)
    lc = line_chunk_space_name(repo_id, dim)
    summary = await AnalysisService.get_summary(repo_id)
    a = summary.get("analysis_summary") or {}
    info = {
        "completed": int(a.get("completed_files") or 0),
        "failed": int(a.get("failed_files") or 0),
        "pending": int(a.get("pending_files") or 0),
        "running": int(a.get("running_files") or 0),
        "symbol_exists": await VECTOR_STORE_CONN.space_exists(ss),
        "line_exists": await VECTOR_STORE_CONN.space_exists(lc),
    }
    if info["symbol_exists"]:
        rows = await VECTOR_STORE_CONN.list_records(
            ss,
            condition={"repo_id": repo_id},
            select_fields=["file_path", "symbol_name"],
            limit=5,
        )
        info["symbol_sample"] = len(rows)
        # count via open
        table = VECTOR_STORE_CONN._open_table(ss)  # type: ignore[attr-defined]
        info["symbol_rows"] = int(table.count_rows())
    if info["line_exists"]:
        table = VECTOR_STORE_CONN._open_table(lc)  # type: ignore[attr-defined]
        info["line_rows"] = int(table.count_rows())
    print(f"[postcheck] {info}", flush=True)
    return info


def main() -> int:
    os.environ["ENABLE_INCREMENTAL_SCAN"] = "false"
    os.environ["PANDO_CLEAR"] = "1"
    os.environ.pop("KB_CLEAR", None)

    from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession
    import pytest

    PandoAgentScenarioSession.run_async(_preflight())
    PandoAgentScenarioSession._vector_ready = False
    PandoAgentScenarioSession._graph_ready = False
    PandoAgentScenarioSession._session_repo_id = None
    PandoAgentScenarioSession._session_repo_path = None

    try:
        async def _rebuild():
            repo_id = await PandoAgentScenarioSession.ensure_vector_ready()
            return await _postcheck(repo_id)

        info = PandoAgentScenarioSession.run_async(_rebuild())
        if info.get("failed", 0) > 0 or info.get("completed", 0) <= 0:
            print(f"[eval] pando bad {info}", flush=True)
            return 3
        if not info.get("symbol_exists") or not info.get("line_exists"):
            print(f"[eval] vector spaces missing {info}", flush=True)
            return 4
        if int(info.get("symbol_rows") or 0) <= 0:
            print(f"[eval] symbol_summary empty {info}", flush=True)
            return 5
    except Exception:
        traceback.print_exc()
        return 2

    os.environ.pop("PANDO_CLEAR", None)
    code = int(
        pytest.main(
            [
                "tests/scenarios/pando_agent/test_similar_accuracy.py",
                "tests/scenarios/pando_agent/test_related_hybrid_accuracy.py",
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
