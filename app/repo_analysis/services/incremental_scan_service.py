from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Set
from sqlalchemy import func, select, update
from app.config.settings import settings
from app.infrastructure.database import get_db_session
from app.repo_analysis.models.analysis_status import (
    FileAnalysisStatus,
    RepoAnalysisStatus,
    RepoAnalysisTask,
    RepoFileAnalysisState,
)
from app.repo_analysis.services.analysis_service import AnalysisService
from app.repo_analysis.services.experience_service import ExperienceService
from app.repo_analysis.services.file_analysis_service import FileAnalysisService
from app.repo_analysis.services.mr_experience.git_history_source import GitHistorySource
from app.repo_analysis.services.repo_path_ignore import RepoPathIgnore
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


class IncrementalScanService:
    """
    后台 tick：对已登记（repo add）的 code/lib 仓做
    变更扫描、首次未完成扫描补跑、失败/卡住文件重处理。
    人工负责登记仓；启动交互 mcb 后由本服务周期处理。
    """

    _task: Optional[asyncio.Task] = None
    _stop_event: Optional[asyncio.Event] = None
    STALE_RUNNING_SEC = 1800

    @staticmethod
    def start() -> bool:
        if not settings.enable_incremental_scan:
            logging.info("增量扫描已关闭（ENABLE_INCREMENTAL_SCAN=false）")
            return False
        task = IncrementalScanService._task
        if task and not task.done():
            return False
        IncrementalScanService._stop_event = asyncio.Event()
        interval = max(float(settings.incremental_scan_interval_sec), 30.0)
        IncrementalScanService._task = asyncio.create_task(
            IncrementalScanService._loop(interval_seconds=interval)
        )
        logging.info(
            "后台 tick 已启动：已登记仓的变更/补扫 + 失败重处理 interval=%ss",
            interval,
        )
        return True

    @staticmethod
    async def stop() -> None:
        stop_event = IncrementalScanService._stop_event
        if stop_event:
            stop_event.set()
        task = IncrementalScanService._task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        IncrementalScanService._stop_event = None
        IncrementalScanService._task = None

    @staticmethod
    async def _loop(interval_seconds: float) -> None:
        await IncrementalScanService.run_once()
        while True:
            try:
                stop_event = IncrementalScanService._stop_event
                if stop_event and stop_event.is_set():
                    return
                await asyncio.sleep(interval_seconds)
                await IncrementalScanService.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error("增量扫描循环异常: %s", e)

    @staticmethod
    async def run_once() -> None:
        async with get_db_session() as db:
            repos = (await db.scalars(select(GitRepository))).all()
        for repo in repos:
            kind = (getattr(repo, "kind", None) or RepoKind.CODE).strip().lower()
            if kind not in (RepoKind.CODE, RepoKind.LIB):
                continue
            if not repo.local_path or not os.path.isdir(repo.local_path):
                continue
            try:
                await IncrementalScanService._recover_stale_running(repo.id)
                await IncrementalScanService._nudge_file_workers(repo.id)
                if not await IncrementalScanService._is_scan_active(repo.id):
                    if await IncrementalScanService._needs_rescan(repo):
                        await AnalysisService.start_scan(repo_id=repo.id)
                        logging.info(
                            "增量扫描触发变更分析 repo_id=%s path=%s kind=%s",
                            repo.id,
                            repo.local_path,
                            kind,
                        )
            except Exception as e:
                logging.warning("增量扫描触发失败 repo_id=%s error=%s", repo.id, e)
            await IncrementalScanService._maybe_trigger_experience_analyze(repo)

    @staticmethod
    async def _recover_stale_running(repo_id: str) -> int:
        """把长时间卡在 RUNNING 的文件重置为 PENDING，便于失败重处理。"""
        cutoff_dt = datetime.now() - timedelta(seconds=IncrementalScanService.STALE_RUNNING_SEC)
        async with get_db_session() as db:
            result = await db.execute(
                update(RepoFileAnalysisState)
                .where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.status == FileAnalysisStatus.RUNNING.value,
                    RepoFileAnalysisState.last_started_at.is_not(None),
                    RepoFileAnalysisState.last_started_at < cutoff_dt,
                )
                .values(
                    status=FileAnalysisStatus.PENDING.value,
                    last_error="stale running recovered by background tick",
                )
            )
            await db.commit()
            return int(result.rowcount or 0)

    @staticmethod
    async def _nudge_file_workers(repo_id: str) -> None:
        """有 PENDING/FAILED 时拉起文件分析 worker（与全局调度互补）。"""
        async with get_db_session() as db:
            cnt = await db.scalar(
                select(func.count())
                .select_from(RepoFileAnalysisState)
                .where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.status.in_(
                        [
                            FileAnalysisStatus.PENDING.value,
                            FileAnalysisStatus.FAILED.value,
                            FileAnalysisStatus.EMBEDDED.value,
                        ]
                    ),
                )
            )
        if int(cnt or 0) <= 0:
            return
        await FileAnalysisService.start_analysis(repo_id)

    @staticmethod
    async def _is_scan_active(repo_id: str) -> bool:
        running = AnalysisService._running_scan_tasks.get(repo_id)
        if running and not running.done():
            return True
        async with get_db_session() as db:
            status = await db.scalar(
                select(RepoAnalysisTask.scan_status).where(RepoAnalysisTask.repo_id == repo_id)
            )
        return status == RepoAnalysisStatus.RUNNING.value

    @staticmethod
    async def _needs_rescan(repo: GitRepository) -> bool:
        kind = (getattr(repo, "kind", None) or RepoKind.CODE).strip().lower()
        extensions = (
            AnalysisService.LIB_EXTENSIONS if kind == RepoKind.LIB else AnalysisService.CODE_EXTENSIONS
        )
        async with get_db_session() as db:
            task = await db.scalar(
                select(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo.id)
            )
            db_file_count = await db.scalar(
                select(func.count())
                .select_from(RepoFileAnalysisState)
                .where(RepoFileAnalysisState.repo_id == repo.id)
            )
        if not task or not task.last_scan_finished_at:
            # 已登记但尚未成功扫完：由后台 tick 拉起（含首次）；人工只需 repo add
            return True

        from app.repo_analysis.services.scan_change_detector import ScanChangeDetector

        git_decision = ScanChangeDetector.needs_rescan_by_git(
            repo.id,
            repo.local_path,
            extensions,
        )
        if git_decision is not None:
            return git_decision

        disk_count = IncrementalScanService._count_source_files(repo.local_path, extensions)
        if int(db_file_count or 0) != disk_count:
            return True
        latest_mtime = IncrementalScanService._max_source_mtime(repo.local_path, extensions)
        if latest_mtime is None:
            return False
        return latest_mtime > task.last_scan_finished_at

    @staticmethod
    async def _maybe_trigger_experience_analyze(repo: GitRepository) -> None:
        if not settings.mr_experience_enabled:
            return
        kind = (getattr(repo, "kind", None) or RepoKind.CODE).strip().lower()
        if kind != RepoKind.CODE:
            return
        if not repo.local_path or not os.path.isdir(repo.local_path):
            return
        try:
            if await ExperienceService.is_job_running(repo.id):
                return
            if not await IncrementalScanService._needs_experience_rescan(repo):
                return
            await ExperienceService.start_analyze(
                repo.id,
                limit=ExperienceService.DEFAULT_ANALYZE_LIMIT,
            )
            logging.info(
                "增量扫描触发 MR 经验分析 repo_id=%s path=%s",
                repo.id,
                repo.local_path,
            )
        except Exception as e:
            logging.warning("增量 MR 经验分析触发失败 repo_id=%s error=%s", repo.id, e)

    @staticmethod
    async def _needs_experience_rescan(repo: GitRepository) -> bool:
        last_sha = await ExperienceService.get_latest_analyzed_commit_sha(repo.id)
        if not last_sha:
            # 从未跑过 experience analyze：首次留给人工
            return False
        return GitHistorySource.has_new_entries(repo.local_path, after_sha=last_sha)

    @staticmethod
    def _count_source_files(repo_root: str, extensions: Set[str]) -> int:
        ignorer = RepoPathIgnore.load(
            repo_root,
            builtin_dir_names=AnalysisService.EXCLUDED_DIRS,
        )
        count = 0
        for parent_root, dirs, files in AnalysisService._iter_scan_directories(repo_root, None):
            ignorer.filter_walk_dirs(parent_root, dirs)
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext not in extensions:
                    continue
                abs_path = os.path.join(parent_root, name)
                rel = os.path.relpath(abs_path, repo_root)
                if ignorer.should_ignore_file(rel):
                    continue
                count += 1
        return count

    @staticmethod
    def _max_source_mtime(repo_root: str, extensions: Set[str]) -> Optional[datetime]:
        ignorer = RepoPathIgnore.load(
            repo_root,
            builtin_dir_names=AnalysisService.EXCLUDED_DIRS,
        )
        latest: Optional[datetime] = None
        for parent_root, dirs, files in AnalysisService._iter_scan_directories(repo_root, None):
            ignorer.filter_walk_dirs(parent_root, dirs)
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext not in extensions:
                    continue
                abs_path = os.path.join(parent_root, name)
                rel = os.path.relpath(abs_path, repo_root)
                if ignorer.should_ignore_file(rel):
                    continue
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(abs_path))
                except OSError:
                    continue
                if latest is None or mtime > latest:
                    latest = mtime
        return latest
