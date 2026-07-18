"""将被测仓 failed/stuck running 重置为 pending，并跑完文件分析调度。"""
from __future__ import annotations
import asyncio
import time
from datetime import datetime
from sqlalchemy import select, update
from app.runtime import ensure_scheduler, init_runtime
from app.infrastructure.database import get_db_session
from app.repo_analysis.models.analysis_status import FileAnalysisStatus, RepoFileAnalysisState
from app.repo_analysis.services.analysis_service import AnalysisService
from app.repo_mgmt.models.git_repo_mgmt import GitRepository


TARGETS = [
    ("61b6ba68-b25c-40ef-af24-125386cfb497", "KnowledegBase-Service"),
    ("c2664c22-3eaa-45eb-b950-d3596667d4c7", "Pando-Agent"),
]
RESET_STATUSES = {
    FileAnalysisStatus.FAILED.value,
    FileAnalysisStatus.RUNNING.value,
}


async def reset_stuck(repo_id: str) -> int:
    async with get_db_session() as db:
        repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
        result = await db.execute(
            update(RepoFileAnalysisState)
            .where(
                RepoFileAnalysisState.repo_id == repo_id,
                RepoFileAnalysisState.status.in_(list(RESET_STATUSES)),
            )
            .values(
                status=FileAnalysisStatus.PENDING.value,
                last_error=None,
                updated_at=datetime.now(),
            )
        )
        await db.commit()
        n = int(result.rowcount or 0)
        print(f"[reset] {getattr(repo, 'local_path', repo_id)} -> pending={n}", flush=True)
        return n


async def summary(repo_id: str) -> dict:
    s = await AnalysisService.get_summary(repo_id)
    a = s.get("analysis_summary") or {}
    scan = s.get("scan") or {}
    return {
        "scan": scan.get("scan_status"),
        "completed": a.get("completed_files"),
        "pending": a.get("pending_files"),
        "running": a.get("running_files"),
        "failed": a.get("failed_files"),
        "active": a.get("scan_active_in_process"),
    }


async def main() -> None:
    await init_runtime()
    await ensure_scheduler()
    for rid, name in TARGETS:
        try:
            await AnalysisService.stop_scan(rid, reason="rebuild failed index")
        except Exception as exc:
            print(f"[stop] {name} {exc}", flush=True)
        await reset_stuck(rid)
        # 不强制全仓重扫：若已有 pending，直接靠调度器消费；无 pending 再 start_scan
        st0 = await summary(rid)
        if int(st0.get("pending") or 0) <= 0:
            await AnalysisService.start_scan(repo_id=rid)
        print(f"[ready] {name} {await summary(rid)}", flush=True)

    deadline = time.time() + 7200
    idle_rounds = 0
    while time.time() < deadline:
        await asyncio.sleep(30)
        done_all = True
        for rid, name in TARGETS:
            st = await summary(rid)
            print(f"[poll] {name} {st}", flush=True)
            pending = int(st.get("pending") or 0)
            running = int(st.get("running") or 0)
            if pending > 0 or running > 0 or st.get("active") or st.get("scan") == "running":
                done_all = False
                idle_rounds = 0
        if done_all:
            idle_rounds += 1
            if idle_rounds >= 2:
                break

    print("==== FINAL ====", flush=True)
    for rid, name in TARGETS:
        async with get_db_session() as db:
            failed = (
                await db.scalars(
                    select(RepoFileAnalysisState).where(
                        RepoFileAnalysisState.repo_id == rid,
                        RepoFileAnalysisState.status == FileAnalysisStatus.FAILED.value,
                    )
                )
            ).all()
        print(f"{name} {await summary(rid)}", flush=True)
        for item in failed[:30]:
            err = (item.last_error or "")[:140]
            print(f"  STILL_FAILED {item.file_path} | {err}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
