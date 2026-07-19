import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict,Optional
from sqlalchemy import delete,select,update
from app.repo_analysis.models.analysis_status import FileAnalysisStatus,RepoFileAnalysisState
from app.repo_mgmt.models.git_repo_mgmt import GitRepository
from app.repo_analysis.services.codeast.ast_analyzer import FileAstAnalyzer
from app.repo_analysis.services.codechunk.code_chunk import CodeChunkService
from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
from app.repo_analysis.services.codevector.code_vector import CodeVectorService
from app.config.settings import settings
from app.infrastructure.database import get_db_session
from app.utils.common import normalize_path, strip_utf8_bom


class FileAnalysisService:
    """从 RepoFileAnalysisState 抢占待处理记录，执行单文件切片/AST/向量化等实际分析。"""

    _MAX_CONCURRENT_REPO_POOLS = 2 # 最大并发仓库分析线程池数量
    _repo_pool_semaphore: Optional[asyncio.Semaphore] = None
    # 全局调度循环相关
    _scheduler_task: Optional[asyncio.Task] = None
    _scheduler_stop_event: Optional[asyncio.Event] = None
    # 仓库分析线程池相关
    _running_tasks: Dict[str, asyncio.Task] = {}

    @staticmethod
    def start_global_scheduler(
        interval_seconds: float = 2.0,
        worker_count: Optional[int] = None,
    ) -> bool:
        """启动全局调度循环。
        Args:
            interval_seconds: 调度间隔时间(秒)。
            worker_count: 每仓worker数量；None 时使用 settings.code_analysis_file_worker_count。
        Returns:
            bool: 是否启动成功。
        """
        if worker_count is None:
            worker_count = settings.code_analysis_file_worker_count
        scheduler_task = FileAnalysisService._scheduler_task
        if scheduler_task and not scheduler_task.done(): # 如果调度任务正在运行，则返回False
            return False
        
        FileAnalysisService._scheduler_stop_event = asyncio.Event() # 设置停止事件
        FileAnalysisService._scheduler_task = asyncio.create_task(
            FileAnalysisService._scheduler_loop(
                interval_seconds=interval_seconds,
                worker_count=worker_count,
            )
        )
        logging.info("文件分析调度器已启动 worker_count=%s interval=%ss", worker_count, interval_seconds)
        return True

    @staticmethod
    async def stop_global_scheduler() -> None:
        """停止全局调度循环。"""
        stop_event = FileAnalysisService._scheduler_stop_event
        scheduler_task = FileAnalysisService._scheduler_task
        # 设置停止事件
        if stop_event:
            stop_event.set()
        # 取消调度任务
        if scheduler_task and not scheduler_task.done(): # 如果调度任务正在运行，则取消
            scheduler_task.cancel()
            try:
                await scheduler_task # 等待调度任务完成
            except (asyncio.CancelledError, RuntimeError):
                # RuntimeError: Future attached to a different loop（跨场景 session 切换）
                pass
        # 清理停止事件和调度任务
        FileAnalysisService._scheduler_stop_event = None
        FileAnalysisService._scheduler_task = None

    @staticmethod
    async def _scheduler_loop(
        interval_seconds: float,
        worker_count: int,
    ) -> None:
        """全局调度循环。
        Args:
            interval_seconds: 调度间隔时间(秒)。
            worker_count: 每仓worker数量。
        """
        poll_interval = max(interval_seconds, 0.5)
        while True:
            try:
                stop_event = FileAnalysisService._scheduler_stop_event
                if stop_event and stop_event.is_set():
                    return

                repo_ids = await FileAnalysisService._list_repos_with_pending_records()
                for repo_id in repo_ids:
                    await FileAnalysisService.start_analysis(
                        repo_id=repo_id,
                        worker_count=worker_count,
                    )
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error("文件分析全局调度循环异常: %s", e)
                await asyncio.sleep(poll_interval)

    @staticmethod
    def _claimable_statuses() -> list[str]:
        return [
            FileAnalysisStatus.PENDING.value,
            FileAnalysisStatus.FAILED.value,
            FileAnalysisStatus.EMBEDDED.value,
        ]

    @staticmethod
    async def _list_repos_with_pending_records() -> list[str]:
        async with get_db_session() as db:
            rows = (
                await db.execute(
                    select(RepoFileAnalysisState.repo_id)
                    .where(
                        RepoFileAnalysisState.status.in_(
                            FileAnalysisService._claimable_statuses()
                        )
                    )
                    .distinct()
                )
            ).all()
            return [str(row[0]) for row in rows if row and row[0]]
    
    @staticmethod
    async def start_analysis(
        repo_id: str,
        worker_count: int = 2,
    ) -> None:
        """幂等启动指定仓库的分析 worker 线程池。"""
        running_task = FileAnalysisService._running_tasks.get(repo_id)
        if running_task and not running_task.done():
            return

        async def worker_pool_runner() -> None:
            try:
                # 获取仓库分析线程池信号量
                async with FileAnalysisService._get_repo_pool_semaphore():
                    workers = [FileAnalysisService._worker_loop(repo_id) for _ in range(max(worker_count, 1))]
                    # 启动worker协程并等待它们完成
                    await asyncio.gather(*workers)
            finally:
                FileAnalysisService._running_tasks.pop(repo_id, None)

        # 创建并记录运行中的任务
        running_task = asyncio.create_task(worker_pool_runner())
        FileAnalysisService._running_tasks[repo_id] = running_task

    @staticmethod
    async def stop_analysis(
        repo_id: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        """停止指定仓库的文件分析 worker（用于删除分析数据前的并发保护）。"""
        running_task = FileAnalysisService._running_tasks.get(repo_id)
        if not running_task or running_task.done():
            FileAnalysisService._running_tasks.pop(repo_id, None)
            return

        running_task.cancel()
        try:
            await asyncio.wait_for(running_task, timeout=timeout_seconds)
        except (asyncio.CancelledError, Exception):
            pass

        FileAnalysisService._running_tasks.pop(repo_id, None)

    @staticmethod
    def _get_repo_pool_semaphore() -> asyncio.Semaphore:
        if FileAnalysisService._repo_pool_semaphore is None:
            FileAnalysisService._repo_pool_semaphore = asyncio.Semaphore(FileAnalysisService._MAX_CONCURRENT_REPO_POOLS)
        return FileAnalysisService._repo_pool_semaphore

    @staticmethod
    async def _worker_loop(
        repo_id: str,
    ) -> None:
        idle_rounds = 0
        while True:
            claimed = await FileAnalysisService._get_one_record_and_mark_running(repo_id)
            if not claimed:
                idle_rounds += 1
                if idle_rounds >= 3:
                    return
                await asyncio.sleep(0.3)
                continue
            idle_rounds = 0
            record, prior_status = claimed
            await FileAnalysisService._analysis_one_file(record.id, prior_status=prior_status)

    @staticmethod
    async def _get_one_record_and_mark_running(
        repo_id: str,
    ) -> Optional[tuple[RepoFileAnalysisState, str]]:
        claimable = FileAnalysisService._claimable_statuses()
        async with get_db_session() as db:
            state = await db.scalar(
                select(RepoFileAnalysisState)
                .where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.status.in_(claimable),
                )
                .order_by(RepoFileAnalysisState.updated_at.asc())
                .limit(1)
            )
            if not state:
                return None
            prior_status = str(state.status or "")
            now = datetime.now()
            try:
                updated = await db.execute(
                    update(RepoFileAnalysisState)
                    .where(
                        RepoFileAnalysisState.id == state.id,
                        RepoFileAnalysisState.status.in_(claimable),
                    )
                    .values(
                        status=FileAnalysisStatus.RUNNING.value,
                        last_started_at=now,
                        last_error=None,
                    )
                )
                if (updated.rowcount or 0) == 0:
                    await db.rollback()
                    return None
                await db.commit()
            except Exception as e:
                try:
                    await db.rollback()
                except Exception:
                    pass
                logging.warning(
                    "标记 repo_file_analysis_state 为 RUNNING 失败 repo_id=%s record_id=%s error=%s",
                    repo_id,
                    state.id,
                    e,
                )
                return None
            return state, prior_status

    @staticmethod
    async def _analysis_one_file(
        record_id: str,
        *,
        prior_status: str = FileAnalysisStatus.PENDING.value,
    ) -> None:
        async with get_db_session() as db:
            record = await db.scalar(select(RepoFileAnalysisState).where(RepoFileAnalysisState.id == record_id))
            if not record:
                return
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == record.repo_id))
            if not repo or not repo.local_path or not os.path.isdir(repo.local_path):
                await FileAnalysisService._finish_record(
                    db=db,
                    record=record,
                    status=FileAnalysisStatus.FAILED.value,
                    last_error="仓库不存在或本地路径不可访问",
                )
                return
            
            abs_file_path = os.path.join(repo.local_path, *record.file_path.split("/"))
            if not os.path.exists(abs_file_path):
                await FileAnalysisService.delete_file_analysis_data(
                    repo_id=record.repo_id,
                    rel_file_path=record.file_path,
                    force=True,
                )
                return

            try:
                from app.repo_mgmt.models.git_repo_mgmt import RepoKind

                kind = getattr(repo, "kind", None) or RepoKind.CODE
                if kind == RepoKind.LIB:
                    from app.lib_analysis.services.file_processor import LibFileProcessor

                    ok, err_detail = await LibFileProcessor.analyze_file(
                        repo_id=record.repo_id,
                        repo_path=repo.local_path,
                        rel_file_path=record.file_path,
                        abs_file_path=abs_file_path,
                    )
                    await FileAnalysisService._finish_record(
                        db=db,
                        record=record,
                        status=(
                            FileAnalysisStatus.COMPLETED.value
                            if ok
                            else FileAnalysisStatus.FAILED.value
                        ),
                        last_error=None if ok else err_detail,
                    )
                    return

                symbol_phase = prior_status == FileAnalysisStatus.EMBEDDED.value
                if symbol_phase:
                    ok, err_detail = await FileAnalysisService._analyze_symbol_phase(
                        repo_id=record.repo_id,
                        repo_path=repo.local_path,
                        rel_file_path=record.file_path,
                        abs_file_path=abs_file_path,
                    )
                    # 符号失败仍保留 embedded：行块可搜，稍后重试摘要
                    await FileAnalysisService._finish_record(
                        db=db,
                        record=record,
                        status=(
                            FileAnalysisStatus.COMPLETED.value
                            if ok
                            else FileAnalysisStatus.EMBEDDED.value
                        ),
                        last_error=None if ok else err_detail,
                    )
                    return

                ok, err_detail, next_status = await FileAnalysisService._analyze_embed_phase(
                    repo_id=record.repo_id,
                    repo_path=repo.local_path,
                    rel_file_path=record.file_path,
                    abs_file_path=abs_file_path,
                )
                if not ok:
                    await FileAnalysisService._finish_record(
                        db=db,
                        record=record,
                        status=FileAnalysisStatus.FAILED.value,
                        last_error=err_detail,
                    )
                    return
                await FileAnalysisService._finish_record(
                    db=db,
                    record=record,
                    status=next_status,
                    last_error=None,
                )
            except Exception as e:
                logging.error("文件分析失败 repo_id=%s file_path=%s error=%s", record.repo_id, record.file_path, e)
                await FileAnalysisService._finish_record(
                    db=db,
                    record=record,
                    status=FileAnalysisStatus.FAILED.value,
                    last_error=str(e),
                )

    @staticmethod
    async def _analyze_embed_phase(
        repo_id: str,
        repo_path: str,
        rel_file_path: str,
        abs_file_path: str,
    ) -> tuple[bool, Optional[str], str]:
        """快路径：AST + 行块 embedding。若还需符号摘要则落到 embedded，否则 completed。"""
        try:
            chunk_on = bool(settings.code_analysis_line_chunk_enabled)
            symbol_on = bool(settings.code_analysis_symbol_summary_enabled)
            if not chunk_on and not symbol_on:
                logging.info(
                    "跳过向量化（chunk/symbol 均关闭）repo_id=%s file_path=%s",
                    repo_id,
                    rel_file_path,
                )
                return True, None, FileAnalysisStatus.COMPLETED.value

            # 仅符号、无行块：本阶段直接做符号并 completed（无 embedding 可搜阶段）
            if not chunk_on and symbol_on:
                ok, err = await FileAnalysisService._analyze_symbol_phase(
                    repo_id, repo_path, rel_file_path, abs_file_path
                )
                return ok, err, FileAnalysisStatus.COMPLETED.value

            source = strip_utf8_bom(Path(abs_file_path).read_text(encoding="utf-8", errors="ignore"))
            file_ext = os.path.splitext(abs_file_path)[1].lower()
            file_info = await FileAstAnalyzer(repo_path, abs_file_path).analyze_file(source=source)
            line_chunks = CodeChunkService.slice_file(abs_file_path, source_text=source)
            if file_info:
                symbol_chunks = CodeChunkService.slice_symbol_bodies(file_info, file_ext=file_ext)
                chunks = CodeChunkService.merge_chunks(line_chunks, symbol_chunks)
            else:
                chunks = line_chunks
            await CodeVectorService.vectorize_and_store_line_chunks(
                repo_id,
                rel_file_path,
                chunks,
            )
            if symbol_on:
                return True, None, FileAnalysisStatus.EMBEDDED.value
            return True, None, FileAnalysisStatus.COMPLETED.value
        except Exception as e:
            logging.error(
                "文件 embedding 阶段失败 repo_id=%s file_path=%s error=%s",
                repo_id,
                rel_file_path,
                e,
            )
            return False, str(e), FileAnalysisStatus.FAILED.value

    @staticmethod
    async def _analyze_symbol_phase(
        repo_id: str,
        repo_path: str,
        rel_file_path: str,
        abs_file_path: str,
    ) -> tuple[bool, Optional[str]]:
        """异步补齐：AST + 符号摘要向量。"""
        try:
            if not bool(settings.code_analysis_symbol_summary_enabled):
                return True, None
            source = strip_utf8_bom(Path(abs_file_path).read_text(encoding="utf-8", errors="ignore"))
            file_info = await FileAstAnalyzer(repo_path, abs_file_path).analyze_file(source=source)
            if not file_info:
                return True, None
            await CodeVectorService.vectorize_and_store_symbol_summaries(
                repo_id,
                rel_file_path,
                file_info,
            )
            return True, None
        except Exception as e:
            logging.error(
                "文件符号摘要阶段失败 repo_id=%s file_path=%s error=%s",
                repo_id,
                rel_file_path,
                e,
            )
            return False, str(e)

    @staticmethod
    async def _finish_record(
        db,
        record: RepoFileAnalysisState,
        status: str,
        last_error: Optional[str],
    ) -> None:
        record.status = status
        record.last_error = last_error
        if status in (
            FileAnalysisStatus.COMPLETED.value,
            FileAnalysisStatus.EMBEDDED.value,
        ):
            record.last_finished_at = datetime.now()
        await db.commit()

    @staticmethod
    async def delete_file_analysis_data(
        repo_id: str,
        rel_file_path: str,
        force: bool = False,
    ) -> Dict[str, object]:
        normalized_file_path = normalize_path(rel_file_path).strip("/")
        async with get_db_session() as db:
            record = await db.scalar(
                select(RepoFileAnalysisState).where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.file_path == normalized_file_path,
                )
            )
            if record and record.status == FileAnalysisStatus.RUNNING.value and not force:
                raise ValueError("该文件分析任务正在运行，无法删除（可使用 force=true 强制删除）")
            
            # 删除文件分析状态记录
            deleted_states = await db.execute(
                delete(RepoFileAnalysisState).where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.file_path == normalized_file_path,
                )
            )
            await db.commit()

        # 删除向量记录（code / lib 分别清理）
        deleted_vectors = await CodeVectorService.delete_file_vector_records(
            repo_id=repo_id,
            rel_file_path=normalized_file_path,
        )
        try:
            from app.lib_analysis.services.api_vector import ApiVectorService

            deleted_vectors += await ApiVectorService.delete_file_vector_records(
                repo_id=repo_id,
                rel_file_path=normalized_file_path,
            )
        except Exception as e:
            logging.warning(
                "删除 Lib API 向量失败 repo_id=%s file_path=%s error=%s",
                repo_id,
                normalized_file_path,
                e,
            )

        # 删除 codegraph 中该文件对应数据
        if settings.code_graph_enabled:
            generator = None
            try:
                generator = CodeGraphGateway.create_generator(repo_id, "", "")
                await generator.delete_file_graph(normalized_file_path)
            except Exception as e:
                logging.warning("删除文件 codegraph 数据失败 repo_id=%s file_path=%s error=%s", repo_id, normalized_file_path, e)
            finally:
                if generator:
                    try:
                        generator.close()
                    except Exception:
                        pass
        return {
            "repo_id": repo_id,
            "file_path": normalized_file_path,
            "deleted_file_states": int(deleted_states.rowcount or 0),
            "deleted_vector_records": int(deleted_vectors),
        }