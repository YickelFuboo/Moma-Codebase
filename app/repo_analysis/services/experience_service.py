from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import delete, func, select, update
from app.infrastructure.database import get_db_session
from app.repo_analysis.models.experience_status import (
    ExperienceItemStatus,
    ExperienceJobStatus,
    MrExperienceItem,
    RepoExperienceTask,
)
from app.repo_analysis.services.mr_experience.change_filter import ChangeFilter
from app.repo_analysis.services.mr_experience.git_history_source import GitHistorySource
from app.repo_analysis.services.mr_experience.models import FileChange
from app.repo_analysis.services.mr_experience.pattern_summarizer import (
    PatternSummarizer,
    PatternSummarizerError,
)
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


class ExperienceService:
    """历史合入经验沉淀编排：采集 → 规则筛选 → LLM → 向量（失败记 failed 并支持重试）。"""

    _running_jobs: Dict[str, asyncio.Task] = {}
    _retry_scheduler_task: Optional[asyncio.Task] = None
    _retry_stop_event: Optional[asyncio.Event] = None
    MAX_RETRY = 5

    @staticmethod
    async def start_analyze(
        repo_id: str,
        *,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, object]:
        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")
            kind = getattr(repo, "kind", None) or RepoKind.CODE
            if kind != RepoKind.CODE:
                raise ValueError(f"experience 仅支持 kind=code，当前 kind={kind}")
            if not repo.local_path:
                raise ValueError("仓库本地路径不可用")
            local_path = repo.local_path

            task = await db.scalar(select(RepoExperienceTask).where(RepoExperienceTask.repo_id == repo_id))
            if task and task.job_status == ExperienceJobStatus.RUNNING.value:
                return ExperienceService._job_to_dict(task)
            if not task:
                task = RepoExperienceTask(repo_id=repo_id, job_status=ExperienceJobStatus.IDLE.value)
                db.add(task)
            task.job_status = ExperienceJobStatus.RUNNING.value
            task.last_error = None
            task.last_started_at = datetime.now()
            task.last_finished_at = None
            await db.commit()

        running = ExperienceService._running_jobs.get(repo_id)
        if running and not running.done():
            return {"repo_id": repo_id, "job_status": ExperienceJobStatus.RUNNING.value, "info": "already running"}

        ExperienceService._running_jobs[repo_id] = asyncio.create_task(
            ExperienceService._run_analyze(repo_id, local_path, since=since, limit=limit)
        )
        ExperienceService.ensure_retry_scheduler()
        return {
            "repo_id": repo_id,
            "job_status": ExperienceJobStatus.RUNNING.value,
            "info": "experience analyze started",
            "since": since,
            "limit": limit,
        }

    @staticmethod
    async def _run_analyze(
        repo_id: str,
        local_path: str,
        *,
        since: Optional[str],
        limit: int,
    ) -> None:
        try:
            entries = GitHistorySource.collect(local_path, since=since, limit=limit)
            created = 0
            async with get_db_session() as db:
                for entry in entries:
                    existing = await db.scalar(
                        select(MrExperienceItem).where(
                            MrExperienceItem.repo_id == repo_id,
                            MrExperienceItem.commit_sha == entry.commit_sha,
                        )
                    )
                    selected = ChangeFilter.select(entry.files)
                    if not selected:
                        continue
                    files_json = json.dumps(
                        [
                            {
                                "path": f.path,
                                "status": f.status,
                                "additions": f.additions,
                                "deletions": f.deletions,
                            }
                            for f in selected
                        ],
                        ensure_ascii=False,
                    )
                    if existing:
                        if existing.status == ExperienceItemStatus.READY.value:
                            continue
                        existing.commit_message = entry.message
                        existing.committed_at = entry.committed_at
                        existing.is_merge = 1 if entry.is_merge else 0
                        existing.candidate_files_json = files_json
                        if existing.status == ExperienceItemStatus.FAILED.value:
                            existing.status = ExperienceItemStatus.PENDING.value
                            existing.retry_count = 0
                            existing.last_error = None
                    else:
                        db.add(
                            MrExperienceItem(
                                repo_id=repo_id,
                                commit_sha=entry.commit_sha,
                                commit_message=entry.message,
                                committed_at=entry.committed_at,
                                is_merge=1 if entry.is_merge else 0,
                                candidate_files_json=files_json,
                                status=ExperienceItemStatus.PENDING.value,
                            )
                        )
                        created += 1
                await db.commit()

            await ExperienceService._process_pending_and_failed(repo_id, include_failed=False)
            await ExperienceService._refresh_counters(repo_id, job_status=ExperienceJobStatus.COMPLETED.value)
            logging.info("experience analyze 完成 repo_id=%s created=%s", repo_id, created)
        except Exception as e:
            logging.error("experience analyze 失败 repo_id=%s error=%s", repo_id, e)
            async with get_db_session() as db:
                task = await db.scalar(select(RepoExperienceTask).where(RepoExperienceTask.repo_id == repo_id))
                if task:
                    task.job_status = ExperienceJobStatus.FAILED.value
                    task.last_error = str(e)
                    task.last_finished_at = datetime.now()
                    await db.commit()
        finally:
            ExperienceService._running_jobs.pop(repo_id, None)

    @staticmethod
    async def _process_pending_and_failed(repo_id: str, *, include_failed: bool) -> None:
        statuses = [ExperienceItemStatus.PENDING.value]
        if include_failed:
            statuses.append(ExperienceItemStatus.FAILED.value)
        while True:
            async with get_db_session() as db:
                item = await db.scalar(
                    select(MrExperienceItem)
                    .where(
                        MrExperienceItem.repo_id == repo_id,
                        MrExperienceItem.status.in_(statuses),
                        MrExperienceItem.retry_count < ExperienceService.MAX_RETRY,
                    )
                    .order_by(MrExperienceItem.updated_at.asc())
                    .limit(1)
                )
                if not item:
                    return
                item_id = item.id
                updated = await db.execute(
                    update(MrExperienceItem)
                    .where(
                        MrExperienceItem.id == item_id,
                        MrExperienceItem.status.in_(statuses),
                    )
                    .values(
                        status=ExperienceItemStatus.RUNNING.value,
                        last_started_at=datetime.now(),
                        last_error=None,
                    )
                )
                if (updated.rowcount or 0) == 0:
                    await db.rollback()
                    continue
                await db.commit()

            await ExperienceService._process_one_item(item_id)
    @staticmethod
    async def _process_one_item(item_id: str) -> None:
        async with get_db_session() as db:
            item = await db.scalar(select(MrExperienceItem).where(MrExperienceItem.id == item_id))
            if not item:
                return
            repo_id = item.repo_id
            commit_sha = item.commit_sha
            message = item.commit_message or ""
            try:
                files_data = json.loads(item.candidate_files_json or "[]")
            except json.JSONDecodeError:
                files_data = []
            files = [
                FileChange(
                    path=str(x.get("path") or ""),
                    status=str(x.get("status") or "M"),
                    additions=int(x.get("additions") or 0),
                    deletions=int(x.get("deletions") or 0),
                )
                for x in files_data
                if isinstance(x, dict) and x.get("path")
            ]

        try:
            if not files:
                raise PatternSummarizerError("候选文件为空")
            pattern = await PatternSummarizer.summarize(message, files, commit_sha)
            await PatternVectorService.upsert_pattern(repo_id, pattern)
            async with get_db_session() as db:
                item = await db.scalar(select(MrExperienceItem).where(MrExperienceItem.id == item_id))
                if not item:
                    return
                item.title = pattern.title
                item.steps_json = json.dumps(
                    [{"file": s.file, "action": s.action} for s in pattern.steps],
                    ensure_ascii=False,
                )
                item.status = ExperienceItemStatus.READY.value
                item.last_error = None
                item.last_finished_at = datetime.now()
                await db.commit()
        except Exception as e:
            logging.warning("经验条目失败 item_id=%s error=%s", item_id, e)
            async with get_db_session() as db:
                item = await db.scalar(select(MrExperienceItem).where(MrExperienceItem.id == item_id))
                if not item:
                    return
                item.status = ExperienceItemStatus.FAILED.value
                item.last_error = str(e)
                item.retry_count = int(item.retry_count or 0) + 1
                item.last_finished_at = datetime.now()
                await db.commit()

    @staticmethod
    async def _refresh_counters(repo_id: str, job_status: Optional[str] = None) -> None:
        async with get_db_session() as db:
            total = await db.scalar(
                select(func.count()).select_from(MrExperienceItem).where(MrExperienceItem.repo_id == repo_id)
            )
            ready = await db.scalar(
                select(func.count())
                .select_from(MrExperienceItem)
                .where(
                    MrExperienceItem.repo_id == repo_id,
                    MrExperienceItem.status == ExperienceItemStatus.READY.value,
                )
            )
            failed = await db.scalar(
                select(func.count())
                .select_from(MrExperienceItem)
                .where(
                    MrExperienceItem.repo_id == repo_id,
                    MrExperienceItem.status == ExperienceItemStatus.FAILED.value,
                )
            )
            task = await db.scalar(select(RepoExperienceTask).where(RepoExperienceTask.repo_id == repo_id))
            if not task:
                task = RepoExperienceTask(repo_id=repo_id)
                db.add(task)
            task.total_items = int(total or 0)
            task.ready_items = int(ready or 0)
            task.failed_items = int(failed or 0)
            if job_status:
                task.job_status = job_status
                task.last_finished_at = datetime.now()
            await db.commit()

    @staticmethod
    async def get_status(repo_id: str) -> Dict[str, object]:
        async with get_db_session() as db:
            task = await db.scalar(select(RepoExperienceTask).where(RepoExperienceTask.repo_id == repo_id))
            if not task:
                return {
                    "repo_id": repo_id,
                    "job_status": ExperienceJobStatus.IDLE.value,
                    "total_items": 0,
                    "ready_items": 0,
                    "failed_items": 0,
                }
            return ExperienceService._job_to_dict(task)

    @staticmethod
    def _job_to_dict(task: RepoExperienceTask) -> Dict[str, object]:
        return {
            "repo_id": task.repo_id,
            "job_status": task.job_status,
            "last_error": task.last_error,
            "last_started_at": task.last_started_at.isoformat() if task.last_started_at else None,
            "last_finished_at": task.last_finished_at.isoformat() if task.last_finished_at else None,
            "total_items": int(task.total_items or 0),
            "ready_items": int(task.ready_items or 0),
            "failed_items": int(task.failed_items or 0),
        }

    @staticmethod
    async def clear(repo_id: str) -> None:
        running = ExperienceService._running_jobs.get(repo_id)
        if running and not running.done():
            running.cancel()
            try:
                await asyncio.wait_for(running, timeout=5)
            except Exception:
                pass
            ExperienceService._running_jobs.pop(repo_id, None)
        async with get_db_session() as db:
            await db.execute(delete(MrExperienceItem).where(MrExperienceItem.repo_id == repo_id))
            await db.execute(delete(RepoExperienceTask).where(RepoExperienceTask.repo_id == repo_id))
            await db.commit()
        try:
            await PatternVectorService.delete_repo_patterns(repo_id)
        except Exception as e:
            logging.warning("清理经验向量失败 repo_id=%s error=%s", repo_id, e)

    @classmethod
    def ensure_retry_scheduler(cls, interval_seconds: float = 30.0) -> None:
        task = cls._retry_scheduler_task
        if task and not task.done():
            return
        cls._retry_stop_event = asyncio.Event()
        cls._retry_scheduler_task = asyncio.create_task(
            cls._retry_loop(interval_seconds=interval_seconds)
        )

    @classmethod
    async def stop_retry_scheduler(cls) -> None:
        if cls._retry_stop_event:
            cls._retry_stop_event.set()
        task = cls._retry_scheduler_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except Exception:
                pass
        cls._retry_scheduler_task = None
        cls._retry_stop_event = None

    @classmethod
    async def _retry_loop(cls, interval_seconds: float) -> None:
        while True:
            try:
                if cls._retry_stop_event and cls._retry_stop_event.is_set():
                    return
                repo_ids = await cls._list_repos_with_failed()
                for repo_id in repo_ids:
                    if repo_id in cls._running_jobs and not cls._running_jobs[repo_id].done():
                        continue
                    await cls._process_pending_and_failed(repo_id, include_failed=True)
                    await cls._refresh_counters(repo_id)
                await asyncio.sleep(max(interval_seconds, 5.0))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error("experience 重试调度异常: %s", e)
                await asyncio.sleep(max(interval_seconds, 5.0))

    @staticmethod
    async def _list_repos_with_failed() -> List[str]:
        async with get_db_session() as db:
            rows = (
                await db.execute(
                    select(MrExperienceItem.repo_id)
                    .where(
                        MrExperienceItem.status == ExperienceItemStatus.FAILED.value,
                        MrExperienceItem.retry_count < ExperienceService.MAX_RETRY,
                    )
                    .distinct()
                )
            ).all()
            return [str(r[0]) for r in rows if r and r[0]]
