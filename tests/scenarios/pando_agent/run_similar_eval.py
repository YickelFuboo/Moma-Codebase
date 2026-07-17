"""Pando similar 定向评测：仅 analyze 用例涉及目录，再跑 6 条 ground truth。"""
from __future__ import annotations
import asyncio
import os
import time
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_SIMILAR_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession

TARGET_DIRS = [
    "app/agents/core",
    "app/agents/context",
    "app/agents/memorys/default",
    "app/utils/auth",
    "app/channel/websocket",
]


async def _analyze_targets(repo_id: str) -> None:
    from app.repo_analysis.models.analysis_status import FileAnalysisStatus, RepoAnalysisStatus
    from app.repo_analysis.services.analysis_service import AnalysisService
    from app.repo_analysis.services.file_analysis_service import FileAnalysisService

    FileAnalysisService.start_global_scheduler(
        interval_seconds=2.0,
        worker_count=PandoAgentScenarioSession.FILE_WORKER_COUNT,
    )
    for rel in TARGET_DIRS:
        print(f"[pando-eval] analyze target={rel}", flush=True)
        await AnalysisService.start_scan(repo_id=repo_id, target_rel_path=rel)
        deadline = time.time() + 1800
        while time.time() < deadline:
            summary = await AnalysisService.get_summary(repo_id)
            scan = summary.get("scan") or {}
            a = summary.get("analysis_summary") or {}
            pending = int(a.get("pending_files") or 0)
            running = int(a.get("running_files") or 0)
            completed = int(a.get("completed_files") or 0)
            scan_status = scan.get("scan_status")
            in_mem = bool(a.get("scan_active_in_process"))
            scan_done = scan_status in (
                RepoAnalysisStatus.COMPLETED.value,
                RepoAnalysisStatus.FAILED.value,
                RepoAnalysisStatus.IDLE.value,
            ) and not in_mem
            if scan_done and pending == 0 and running == 0:
                print(
                    f"[pando-eval] target done {rel} completed={completed}",
                    flush=True,
                )
                break
            await asyncio.sleep(3)
    await FileAnalysisService.stop_global_scheduler()


async def main() -> None:
    os.environ["PANDO_CLEAR"] = "0"
    PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = False
    PandoAgentScenarioSession.require_repo_or_skip()
    repo_id = await PandoAgentScenarioSession.ensure_repo()
    PandoAgentScenarioSession.apply_feature_flags()
    await _analyze_targets(repo_id)
    PandoAgentScenarioSession._vector_ready = True
    scores = []
    for case in PANDO_SIMILAR_CASES:
        result = await PandoAgentScenarioSession.search_similar(
            case.extra["code"],
            top_k=case.top_k,
        )
        hits = [it.get("file_path") for it in (result.get("items") or [])]
        score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
        scores.append(score)
        top = (result.get("items") or [{}])[0]
        print(
            "[pando-similar] {cid} P={p:.2%} R={r:.2%} top={top} fused={fs} vec={vs} lex={ls}".format(
                cid=case.case_id,
                p=score.precision,
                r=score.recall,
                top=top.get("file_path"),
                fs=top.get("score"),
                vs=top.get("vector_score"),
                ls=top.get("lexical_score"),
            ),
            flush=True,
        )
    avg_p = sum(s.precision for s in scores) / len(scores)
    avg_r = sum(s.recall for s in scores) / len(scores)
    passed = sum(
        1
        for s, c in zip(scores, PANDO_SIMILAR_CASES)
        if s.recall >= c.min_recall and s.precision >= c.min_precision
    )
    print(
        "SUMMARY cases={n} pass={passed}/{n} avg_P={p:.2%} avg_R={r:.2%}".format(
            n=len(scores),
            passed=passed,
            p=avg_p,
            r=avg_r,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
