import asyncio
import logging
import os
from datetime import datetime
from typing import Dict,Iterable,List,Optional,Set,Tuple
from sqlalchemy import delete,func,or_,select,update
from sqlalchemy.exc import IntegrityError
from app.code_analysis.models.analysis_status import FileAnalysisStatus,RepoAnalysisStatus,RepoAnalysisTask,RepoFileAnalysisState
from app.repo_mgmt.models.git_repo_mgmt import GitRepository
from app.code_analysis.services.codegraph.graph_creator import CodeGraphGenerator
from app.code_analysis.services.file_analysis_service import FileAnalysisService
from app.code_analysis.services.codevector.code_vector import CodeVectorService
from app.infrastructure.database import get_db_session
from app.utils.common import normalize_path


class RepoScanCancelled(Exception):
    """扫描协作取消（通过数据库的 scan_status 触发）。"""


class RepoAnalysisService:
    """统一编排服务：扫描仓库并驱动文件级分析消费。"""

    _running_scan_tasks: Dict[str, asyncio.Task] = {}
    _running_graph_tasks: Dict[str, asyncio.Task] = {}
    CODE_EXTENSIONS = {".py", ".java", ".go", ".cpp", ".c"}
    EXCLUDED_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "venv", "node_modules", "dist", "build", "target", ".pytest_cache", ".mypy_cache", ".coverage", "__tests__", "tests"}

    @staticmethod
    async def start_scan(
        repo_id: str,
        target_rel_path: Optional[str] = None,
    ) -> Dict[str, object]:
        """启动仓库扫描：先扫描仓库，再启动文件级分析 worker。
        Args:
            repo_id: 代码仓ID。
            target_rel_path: 目标文件或目录路径（相对仓库根）。
        Returns:
            Dict[str, object]: 扫描结果。
        """
        repo_path: Optional[str] = None
        normalized_target_rel_path: Optional[str] = None
        is_directory: Optional[bool] = None

        async with get_db_session() as db:
            # 获取仓库信息
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")
            if not repo.local_path or not os.path.isdir(repo.local_path):
                raise ValueError("仓库本地路径不存在或不可访问")
            repo_path = repo.local_path
            
            # 获取扫描任务
            task = await db.scalar(select(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo_id))
            if not task:
                task = RepoAnalysisTask(
                    repo_id=repo_id,
                    scan_status=RepoAnalysisStatus.IDLE.value,
                )
                db.add(task)
                await db.commit()
            if task and task.scan_status == RepoAnalysisStatus.RUNNING.value:
                return RepoAnalysisService._scan_task_to_dict(task, repo.local_path)
            
            # 解析目标路径类型
            if target_rel_path:
                is_directory, normalized_target_rel_path = RepoAnalysisService._resolve_target_type(repo.local_path, target_rel_path)
            
            # 获取扫描锁
            acquired_run_lock = await RepoAnalysisService._acquire_scan_lock(
                db=db,
                repo_id=repo_id,
                task=task,
            )
            if not acquired_run_lock:
                # 如果获取扫描锁失败，则返回当前任务状态
                if task:
                    return RepoAnalysisService._scan_task_to_dict(task, repo.local_path)
                return {
                    "repo_id": repo_id,
                    "repo_path": repo.local_path,
                    "scan_status": RepoAnalysisStatus.RUNNING.value,
                    "last_error": None,
                    "last_scan_started_at": None,
                    "last_scan_finished_at": None,
                    "scan_heartbeat_at": None,
                }
        
        # 如果扫描任务正在运行，则返回当前任务状态
        if repo_id in RepoAnalysisService._running_scan_tasks and not RepoAnalysisService._running_scan_tasks[repo_id].done():
            # 如果获取扫描锁成功，则返回当前任务状态
            return {
                "repo_id": repo_id,
                "repo_path": repo_path,
                "scan_status": RepoAnalysisStatus.RUNNING.value,
                "target_rel_path": normalized_target_rel_path,
                "is_directory": is_directory,
                "info": "scan is running",
            }

        # 启动扫描任务
        scanning_task = asyncio.create_task(
            RepoAnalysisService._run_scan(
                repo_id=repo_id,
                repo_path=repo_path or "",
                target_rel_path=normalized_target_rel_path,
                is_directory=is_directory or False,
            )
        )
        RepoAnalysisService._running_scan_tasks[repo_id] = scanning_task

        # 同步启动代码图谱生成（后台任务，不阻塞扫描启动返回）
        existing_graph_task = RepoAnalysisService._running_graph_tasks.get(repo_id)
        if not existing_graph_task or existing_graph_task.done():
            async def _run_graph() -> None:
                try:
                    generator = CodeGraphGenerator(
                        repo_id=repo_id,
                        repo_name=str(repo_id),
                        repo_local_path=repo_path or "",
                    )
                    await generator.generate_graph(clean_stale=True)
                except Exception as e:
                    logging.warning("代码图谱生成失败 repo_id=%s error=%s", repo_id, e)

            RepoAnalysisService._running_graph_tasks[repo_id] = asyncio.create_task(_run_graph())

        return {
            "repo_id": repo_id,
            "repo_path": repo_path,
            "scan_status": RepoAnalysisStatus.RUNNING.value,
            "target_rel_path": normalized_target_rel_path,
            "is_directory": is_directory,
            "info": "scan is running",
        } 

    @staticmethod
    async def _assert_scan_is_running(db, repo_id: str) -> None:
        """如果上层已把 scan_status 从 RUNNING 改掉，则尽快停止扫描。"""
        status_value = await db.scalar(
            select(RepoAnalysisTask.scan_status).where(RepoAnalysisTask.repo_id == repo_id)
        )
        if status_value != RepoAnalysisStatus.RUNNING.value:
            raise RepoScanCancelled("scan cancelled by scan_status change")
    
    @staticmethod
    async def _acquire_scan_lock(
        db,
        repo_id: str,
        task: Optional[RepoAnalysisTask],
    ) -> bool:
        payload = {
            "last_error": None,
            "last_scan_started_at": datetime.now(),
            "last_scan_finished_at": None,
            "scan_heartbeat_at": datetime.now(),
        }

        # 如果扫描任务不存在，则创建扫描任务
        if task is None:
            try:
                db.add(RepoAnalysisTask(
                    repo_id=repo_id,
                    scan_status=RepoAnalysisStatus.RUNNING.value,
                    **payload,
                ))
                await db.commit()
                return True
            except IntegrityError:
                await db.rollback()
        
        # 如果扫描任务存在，则更新扫描任务状态为运行中
        updated = await db.execute(
            update(RepoAnalysisTask)
            .where(
                RepoAnalysisTask.repo_id == repo_id,
                RepoAnalysisTask.scan_status.in_([
                    RepoAnalysisStatus.IDLE.value,
                    RepoAnalysisStatus.COMPLETED.value,
                    RepoAnalysisStatus.FAILED.value,
                ]),
            )
            .values(
                scan_status=RepoAnalysisStatus.RUNNING.value,
                **payload,
            )
        )
        await db.commit()
        return (updated.rowcount or 0) > 0

    @staticmethod
    async def _run_scan(
        repo_id: str,
        repo_path: str,
        target_rel_path: Optional[str],
        is_directory: bool,
    ) -> None:
        try:
            async with get_db_session() as db:
                await RepoAnalysisService._assert_scan_is_running(db, repo_id)
            
            if target_rel_path is not None:
                target_rel_path = normalize_path(target_rel_path.strip())
            
            if target_rel_path is not None and not is_directory:
                scanned_count = 0
                async with get_db_session() as db:
                    abs_path = os.path.normpath(os.path.join(repo_path, *target_rel_path.split("/")))
                    ok = await RepoAnalysisService.update_file_state(db, repo_id, abs_path, target_rel_path)
                    if ok:
                        await RepoAnalysisService._touch_scan_heartbeat(db, repo_id)
                    await db.commit()
                    scanned_count = 1 if ok else 0
            else:
                scanned_count, excluded_dirs = await RepoAnalysisService._scan_dir_and_update_file_states(
                    repo_id=repo_id,
                    repo_root=repo_path,
                    target_rel_path=target_rel_path,
                )

                # 删除排除的子目录下历史状态
                await RepoAnalysisService._delete_files_under_excluded_dirs(
                    repo_id=repo_id,
                    excluded_dirs=excluded_dirs,
                )
            
            if target_rel_path and scanned_count == 0:
                raise ValueError("未匹配到需要重分析的文件")
            
            await RepoAnalysisService._finish_scan_task(
                repo_id=repo_id,
                status=RepoAnalysisStatus.COMPLETED.value,
                last_error=None,
            )
        except RepoScanCancelled as e:
            logging.info("repo扫描已取消 repo_id=%s error=%s", repo_id, e)
            await RepoAnalysisService._finish_scan_task(
                repo_id=repo_id,
                status=RepoAnalysisStatus.FAILED.value,
                last_error="scan cancelled",
            )
        except Exception as e:
            logging.error("repo扫描失败 repo_id=%s error=%s", repo_id, e)
            await RepoAnalysisService._finish_scan_task(
                repo_id=repo_id,
                status=RepoAnalysisStatus.FAILED.value,
                last_error=str(e),
            )
        finally:
            RepoAnalysisService._running_scan_tasks.pop(repo_id, None)

    @staticmethod
    async def _scan_dir_and_update_file_states(
        repo_id: str,
        repo_root: str,
        target_rel_path: Optional[str],
    ) -> Tuple[int, Set[str]]:
        """扫描并更新文件级分析状态。
        Args:
            repo_id: 代码仓ID。
            repo_root: 仓库根路径。
            target_rel_path: 目标文件或目录路径（相对仓库根）。
        Returns:
            Tuple[int, Set[str]]: 本次成功扫描到的代码文件数量；剪枝掉的排除子目录相对路径集合（用于删除其下历史状态，不占全量路径内存）。
        """
        scanned_code_files = 0
        excluded_dirs: Set[str] = set()
        async with get_db_session() as db:
            batch = 0
            
            # 迭代扫描目录
            for parent_root, dirs, files in RepoAnalysisService._iter_scan_directories(repo_root=repo_root, target_rel_path=target_rel_path):
                await RepoAnalysisService._assert_scan_is_running(db, repo_id)
                pruned: List[str] = []
                for d in dirs:
                    # 过滤排除目录
                    if d in RepoAnalysisService.EXCLUDED_DIRS or d.startswith("."):
                        sub_abs = os.path.join(parent_root, d)
                        rel_sub = normalize_path(os.path.relpath(sub_abs, repo_root))
                        if rel_sub != ".":
                            excluded_dirs.add(rel_sub)
                    else:
                        pruned.append(d)
                dirs[:] = pruned
                
                # 处理文件
                direct_file_paths: Set[str] = set()
                for filename in files:
                    abs_path = os.path.join(parent_root, filename)
                    rel_path = normalize_path(os.path.relpath(abs_path, repo_root))
                    ok = await RepoAnalysisService.update_file_state(db, repo_id, abs_path, rel_path)
                    if not ok:
                        continue
                    direct_file_paths.add(rel_path)
                    scanned_code_files += 1
                    batch += 1
                    if batch >= 200:
                        await RepoAnalysisService._touch_scan_heartbeat(db, repo_id)
                        await db.commit()
                        batch = 0
                    
                # 删除目录中缺失的文件级分析状态记录
                await RepoAnalysisService._delete_missing_files_in_cur_dir(
                    db=db,
                    repo_id=repo_id,
                    repo_root=repo_root,
                    cur_dir=parent_root,
                    existing_files=direct_file_paths,
                )
        
            if batch > 0:
                await RepoAnalysisService._touch_scan_heartbeat(db, repo_id)
                await db.commit()
        return scanned_code_files, excluded_dirs

    @staticmethod
    def _iter_scan_directories(
        repo_root: str,
        target_rel_path: Optional[str],
    ) -> Iterable[tuple[str, list[str], list[str]]]:
        """迭代扫描目录。
        Args:
            repo_root: 仓库根路径。
            target_rel_path: 目标文件或目录路径（相对仓库根）。
        Returns:
            Iterable[tuple[str, list[str], list[str]]]: 迭代器，每个元素为(当前根目录, 目录列表, 文件列表)。
        """
        if not target_rel_path:
            yield from os.walk(repo_root)
            return
        
        abs_target = os.path.normpath(os.path.join(repo_root, *target_rel_path.split("/")))
        if not os.path.isdir(abs_target):
            return
        yield from os.walk(abs_target)

    @staticmethod
    def _should_refresh_state(
        state: RepoFileAnalysisState,
        file_modified_at: datetime,
    ) -> bool:
        if state.last_finished_at is None:
            return True
        return file_modified_at > state.last_finished_at

    @staticmethod
    async def update_file_state(
        db,
        repo_id: str,
        abs_file_path: str,
        rel_file_path: str,
    ) -> bool:
        if not os.path.isfile(abs_file_path):
            await db.execute(
                delete(RepoFileAnalysisState).where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.file_path == rel_file_path,
                )
            )
            return False
        
        # 过滤非代码文件    
        ext = os.path.splitext(abs_file_path)[1].lower()
        if ext not in RepoAnalysisService.CODE_EXTENSIONS:
            await db.execute(
                delete(RepoFileAnalysisState).where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.file_path == rel_file_path,
                )
            )
            return False
        
        # 更新文件级分析状态
        record = await db.scalar(
            select(RepoFileAnalysisState).where(
                RepoFileAnalysisState.repo_id == repo_id,
                RepoFileAnalysisState.file_path == rel_file_path,
            )
        )
        if record is None:
            db.add(RepoFileAnalysisState(
                repo_id=repo_id,
                file_path=rel_file_path,
                status=FileAnalysisStatus.PENDING.value,
            ))
        else:
            file_modified_at = datetime.fromtimestamp(os.path.getmtime(abs_file_path))
            if RepoAnalysisService._should_refresh_state(record, file_modified_at):
                record.status = FileAnalysisStatus.PENDING.value
                record.last_error = None
        return True

    @staticmethod
    async def _touch_scan_heartbeat(
        db,
        repo_id: str,
    ) -> None:
        """更新扫描心跳。"""
        task = await db.scalar(select(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo_id))
        if task:
            task.scan_heartbeat_at = datetime.now()

    @staticmethod
    async def _delete_missing_files_in_cur_dir(
        db,
        repo_id: str,
        repo_root: str,
        cur_dir: str,
        existing_files: Set[str],
    ) -> None:
        """删除目录中缺失的文件级分析状态记录。
        Args:
            db: 数据库会话。
            repo_id: 代码仓ID。
            repo_root: 仓库根路径。
            current_root: 当前根目录。
            existing_files: 现有文件集合。
        """
        rel_dir = normalize_path(os.path.relpath(cur_dir, repo_root))
        if rel_dir == ".":
            rel_dir = ""
        
        if rel_dir:
            like_prefix = f"{rel_dir}/%"
            rows = (await db.scalars(
                select(RepoFileAnalysisState.file_path).where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.file_path.like(like_prefix),
                )
            )).all()
            file_paths = [p for p in rows if os.path.dirname(p) == rel_dir]
        else:
            rows = (await db.scalars(
                select(RepoFileAnalysisState.file_path).where(
                    RepoFileAnalysisState.repo_id == repo_id,
                )
            )).all()
            file_paths = [p for p in rows if "/" not in p]
        
        delete_paths = [p for p in file_paths if p not in existing_files]
        if delete_paths:
            await db.execute(
                delete(RepoFileAnalysisState).where(
                    RepoFileAnalysisState.repo_id == repo_id,
                    RepoFileAnalysisState.file_path.in_(delete_paths),
                )
            )

    @staticmethod
    async def _delete_files_under_excluded_dirs(
        repo_id: str,
        excluded_dirs: Set[str],
    ) -> None:
        """删除目录中排除的文件级分析状态记录。
        Args:
            repo_id: 代码仓ID。
            excluded_dirs: 排除的目录集合。
        """
        if not excluded_dirs:
            return
        
        async with get_db_session() as db:
            conds = []
            for p in excluded_dirs:
                conds.append(RepoFileAnalysisState.file_path == p)
                conds.append(RepoFileAnalysisState.file_path.like(f"{p}/%"))
            file_paths = (
                await db.scalars(
                    select(RepoFileAnalysisState.file_path).where(
                        RepoFileAnalysisState.repo_id == repo_id,
                        or_(*conds),
                    )
                )
            ).all()

        for rel_file_path in file_paths:
            try:
                await FileAnalysisService.delete_file_analysis_data(
                    repo_id=repo_id,
                    rel_file_path=rel_file_path,
                    force=True,
                )
            except Exception as e:
                logging.warning("删除 excluded_dirs 下文件分析数据失败 repo_id=%s file_path=%s error=%s", repo_id, rel_file_path, e)

    @staticmethod
    async def _finish_scan_task(
        repo_id: str,
        status: str,
        last_error: Optional[str],
    ) -> None:
        async with get_db_session() as db:
            task = await db.scalar(select(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo_id))
            if not task:
                return
            task.scan_status = status
            task.last_error = last_error
            task.last_scan_finished_at = datetime.now()
            task.scan_heartbeat_at = datetime.now()
            await db.commit()

    @staticmethod
    def _scan_task_to_dict(
        task: RepoAnalysisTask,
        repo_path: Optional[str],
    ) -> Dict[str, object]:
        return {
            "repo_id": task.repo_id,
            "repo_path": repo_path,
            "scan_status": task.scan_status,
            "last_error": task.last_error,
            "last_scan_started_at": task.last_scan_started_at.isoformat() if task.last_scan_started_at else None,
            "last_scan_finished_at": task.last_scan_finished_at.isoformat() if task.last_scan_finished_at else None,
            "scan_heartbeat_at": task.scan_heartbeat_at.isoformat() if task.scan_heartbeat_at else None,
        }

    @staticmethod
    def _resolve_target_type(
        repo_root: str,
        target_rel_path: str,
    ) -> tuple[bool, str]:
        """解析目标路径类型：是否为目录、规范化路径。
        Args:
            repo_root: 仓库根路径。
            target_rel_path: 目标文件或目录路径（相对仓库根）。
        Returns:
            tuple[bool, str]: 是否为目录、规范化路径。
        """
        raw = target_rel_path.strip()
        if not raw:
            raise ValueError("target_rel_path 不能为空")
        
        normalized_slash = normalize_path(raw)
        dir_hint = normalized_slash.endswith("/")
        norm = normalized_slash.strip("/")
        if not norm:
            raise ValueError("target_rel_path 不能为空")
        
        abs_target = os.path.normpath(os.path.join(repo_root, *norm.split("/")))
        if os.path.lexists(abs_target):
            return os.path.isdir(abs_target), norm
        
        if dir_hint:
            return True, norm
        raise ValueError(f"路径在仓库中不存在或无可分析的源码文件: {target_rel_path}")

    @staticmethod
    async def get_summary(
        repo_id: str,
    ) -> Dict[str, object]:
        async with get_db_session() as db:
            rows = (await db.execute(
                select(
                    RepoFileAnalysisState.status,
                    func.count(RepoFileAnalysisState.id),
                )
                .where(RepoFileAnalysisState.repo_id == repo_id)
                .group_by(RepoFileAnalysisState.status)
            )).all()

            # 统计各状态文件数量
            by_status: Dict[str, int] = {}
            total = 0
            for status, cnt in rows:
                count = int(cnt or 0)
                total += count
                by_status[status] = by_status.get(status, 0) + count
            scan = await RepoAnalysisService.get_scan_status(repo_id)
            analysis_summary = {
                "total_files": total,
                "pending_files": by_status.get(FileAnalysisStatus.PENDING.value, 0),
                "running_files": by_status.get(FileAnalysisStatus.RUNNING.value, 0),
                "completed_files": by_status.get(FileAnalysisStatus.COMPLETED.value, 0),
                "failed_files": by_status.get(FileAnalysisStatus.FAILED.value, 0),
                "skipped_files": by_status.get(FileAnalysisStatus.SKIPPED.value, 0),
            }
            return {
                "repo_id": repo_id,
                "scan": scan,
                "analysis_summary": analysis_summary,
            }

    @staticmethod
    async def get_scan_status(
        repo_id: str,
    ) -> Dict[str, object]:
        async with get_db_session() as db:
            task = await db.scalar(select(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo_id))
            if not task:
                return {
                    "repo_id": repo_id,
                    "scan_status": RepoAnalysisStatus.IDLE.value,
                    "last_error": None,
                    "last_scan_started_at": None,
                    "last_scan_finished_at": None,
                    "scan_heartbeat_at": None,
                }
            return RepoAnalysisService._scan_task_to_dict(task, None)

    @staticmethod
    async def stop_scan(
        repo_id: str,
        reason: str = "scan stopped by user",
    ) -> Dict[str, object]:
        async with get_db_session() as db:
            task = await db.scalar(select(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo_id))
            if not task:
                return {
                    "repo_id": repo_id,
                    "scan_status": RepoAnalysisStatus.IDLE.value,
                    "last_error": None,
                    "last_scan_started_at": None,
                    "last_scan_finished_at": None,
                    "scan_heartbeat_at": None,
                }

            now = datetime.now()
            task.scan_status = RepoAnalysisStatus.FAILED.value
            task.last_error = reason
            task.last_scan_finished_at = now
            task.scan_heartbeat_at = now
            await db.commit()
            await db.refresh(task)
        
        running_task = RepoAnalysisService._running_scan_tasks.get(repo_id)
        if running_task and not running_task.done():
            running_task.cancel()
            try:
                await asyncio.wait_for(running_task, timeout=5)
            except Exception:
                pass

        return RepoAnalysisService._scan_task_to_dict(task, None)

    @staticmethod
    async def delete_repo_analysis_data(
        repo_id: str,
    ) -> None:
        try:
            await FileAnalysisService.stop_analysis(repo_id)
        except Exception as e:
            logging.warning("停止文件分析 worker 失败 repo_id=%s error=%s", repo_id, e)

        async with get_db_session() as db:
            task = await db.scalar(select(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo_id))
            if task and task.scan_status == RepoAnalysisStatus.RUNNING.value:
                await RepoAnalysisService.stop_scan(
                    repo_id=repo_id,
                    reason="delete repo analysis data (force stop scan)",
                )

            await db.execute(delete(RepoAnalysisTask).where(RepoAnalysisTask.repo_id == repo_id))
            await db.execute(delete(RepoFileAnalysisState).where(RepoFileAnalysisState.repo_id == repo_id))
            await db.commit()

        try:
            await CodeVectorService.delete_repo_vector_records(repo_id)
        except Exception as e:
            logging.warning("删除 repo 向量数据失败 repo_id=%s error=%s", repo_id, e)

        # 删除 codegraph 中该 repo 的全部数据
        try:
            generator = CodeGraphGenerator(repo_id,"","")
            await generator.delete_repo_graph()
        except Exception as e:
            logging.warning("删除 repo codegraph 数据失败 repo_id=%s error=%s", repo_id, e)
        finally:
            try:
                generator.close()
            except Exception:
                pass
