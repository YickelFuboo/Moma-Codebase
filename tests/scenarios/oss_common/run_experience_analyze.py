"""开源仓 MR 经验提炼（阻塞等待完成）。

用法：
  EXPERIENCE_PATH=F:\\开源项目\\go EXPERIENCE_LIMIT=50 EXPERIENCE_CLEAR=1 \\
    python -m tests.scenarios.oss_common.run_experience_analyze

  或一次跑多仓（逗号分隔）：
  EXPERIENCE_PATHS=F:\\开源项目\\go,F:\\开源项目\\django \\
    python -m tests.scenarios.oss_common.run_experience_analyze
"""
from __future__ import annotations
import asyncio
import os
import sys
from app.cli.common import get_repo_by_path
from app.repo_analysis.services.experience_service import ExperienceService
from app.repo_mgmt.models.git_repo_mgmt import RepoKind
from app.runtime import init_runtime, release_runtime


def _parse_paths() -> list[str]:
    multi = (os.environ.get("EXPERIENCE_PATHS") or "").strip()
    if multi:
        return [p.strip() for p in multi.split(",") if p.strip()]
    single = (os.environ.get("EXPERIENCE_PATH") or "").strip()
    if single:
        return [single]
    raise SystemExit("请设置 EXPERIENCE_PATH 或 EXPERIENCE_PATHS")


def _limit() -> int:
    raw = (os.environ.get("EXPERIENCE_LIMIT") or "50").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 50


def _should_clear() -> bool:
    return os.environ.get("EXPERIENCE_CLEAR", "").strip() in {"1", "true", "True"}


async def _run_one(path: str, *, limit: int, clear: bool) -> dict:
    repo = await get_repo_by_path(path)
    kind = getattr(repo, "kind", None) or RepoKind.CODE
    if kind != RepoKind.CODE:
        raise RuntimeError(f"experience 仅支持 kind=code，当前 kind={kind} path={path}")
    if clear:
        print(f"[experience] clear path={path} repo_id={repo.id}", flush=True)
        await ExperienceService.clear(repo.id)
    print(
        f"[experience] start path={path} repo_id={repo.id} limit={limit}",
        flush=True,
    )
    started = await ExperienceService.start_analyze(repo.id, limit=limit)
    print(f"[experience] started={started}", flush=True)
    job = ExperienceService._running_jobs.get(repo.id)
    if job is not None:
        await job
    status = await ExperienceService.get_status(repo.id)
    status["path"] = path
    print(f"[experience] done status={status}", flush=True)
    return status


async def main() -> int:
    paths = _parse_paths()
    limit = _limit()
    clear = _should_clear()
    await init_runtime()
    results: list[dict] = []
    try:
        for path in paths:
            results.append(await _run_one(path, limit=limit, clear=clear))
    finally:
        await ExperienceService.stop_retry_scheduler()
        await release_runtime()
    failed = [r for r in results if str(r.get("job_status") or "") == "failed"]
    if failed:
        print(f"[experience] FAILED repos={len(failed)}", flush=True)
        return 1
    print(f"[experience] ALL_OK repos={len(results)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
