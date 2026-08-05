import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.config.settings import settings
from app.repo_analysis.models.analysis_status import RepoAnalysisTask
from app.repo_analysis.services.incremental_scan_service import IncrementalScanService
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


class TestIncrementalScanDetection:
    def test_needs_rescan_when_never_scanned(self, tmp_path: Path):
        """已登记但从未扫完：后台 tick 应拉起分析。"""
        repo = GitRepository(
            id="r1",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )
        (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(side_effect=[None, 0])
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await IncrementalScanService._needs_rescan(repo)

        assert asyncio.run(_run()) is True

    def test_needs_rescan_when_file_mtime_newer(self, tmp_path: Path):
        repo = GitRepository(
            id="r2",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )
        f = tmp_path / "svc.py"
        f.write_text("def run(): pass\n", encoding="utf-8")
        task = RepoAnalysisTask(
            repo_id="r2",
            last_scan_finished_at=datetime.now() - timedelta(hours=1),
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(side_effect=[task, 1])
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await IncrementalScanService._needs_rescan(repo)

        assert asyncio.run(_run()) is True

    def test_skip_rescan_when_no_changes(self, tmp_path: Path):
        repo = GitRepository(
            id="r3",
            local_path=str(tmp_path),
            kind=RepoKind.LIB,
        )
        f = tmp_path / "api.py"
        f.write_text("def api(): pass\n", encoding="utf-8")
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        task = RepoAnalysisTask(
            repo_id="r3",
            last_scan_finished_at=mtime + timedelta(seconds=5),
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(side_effect=[task, 1])
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await IncrementalScanService._needs_rescan(repo)

        assert asyncio.run(_run()) is False


class TestIncrementalScanScheduler:
    def test_start_respects_disabled_setting(self, monkeypatch):
        monkeypatch.setattr(
            "app.repo_analysis.services.incremental_scan_service.settings.enable_incremental_scan",
            False,
        )
        assert IncrementalScanService.start() is False

    def test_run_once_triggers_scan_for_changed_repo(self, monkeypatch, tmp_path: Path):
        repo = GitRepository(
            id="r4",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )
        (tmp_path / "main.py").write_text("print('x')\n", encoding="utf-8")

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [repo]))
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch.object(
                    IncrementalScanService,
                    "_is_scan_active",
                    AsyncMock(return_value=False),
                ):
                    with patch.object(
                        IncrementalScanService,
                        "_needs_rescan",
                        AsyncMock(return_value=True),
                    ):
                        with patch.object(
                            IncrementalScanService,
                            "_recover_stale_running",
                            AsyncMock(return_value=0),
                        ):
                            with patch.object(
                                IncrementalScanService,
                                "_nudge_file_workers",
                                AsyncMock(),
                            ):
                                start_scan = AsyncMock()
                                with patch(
                                    "app.repo_analysis.services.incremental_scan_service.AnalysisService.start_scan",
                                    start_scan,
                                ):
                                    await IncrementalScanService.run_once()
                                    start_scan.assert_awaited_once_with(repo_id="r4")

        asyncio.run(_run())

    def test_run_once_triggers_experience_analyze_for_new_mrs(self, monkeypatch, tmp_path: Path):
        repo = GitRepository(
            id="r5",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )
        (tmp_path / "main.py").write_text("print('x')\n", encoding="utf-8")

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [repo]))
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch.object(
                    IncrementalScanService,
                    "_is_scan_active",
                    AsyncMock(return_value=False),
                ):
                    with patch.object(
                        IncrementalScanService,
                        "_needs_rescan",
                        AsyncMock(return_value=False),
                    ):
                        with patch.object(
                            IncrementalScanService,
                            "_get_last_collected_sha",
                            AsyncMock(return_value="abc123"),
                        ):
                            with patch.object(
                                IncrementalScanService,
                                "_recover_stale_running",
                                AsyncMock(return_value=0),
                            ):
                                with patch.object(
                                    IncrementalScanService,
                                    "_nudge_file_workers",
                                    AsyncMock(),
                                ):
                                    with patch(
                                        "app.repo_analysis.services.incremental_scan_service.ExperienceService.is_job_running",
                                        AsyncMock(return_value=False),
                                    ):
                                        start_analyze = AsyncMock()
                                        with patch(
                                            "app.repo_analysis.services.incremental_scan_service.ExperienceService.start_analyze",
                                            start_analyze,
                                        ):
                                            with patch(
                                                "app.repo_analysis.services.incremental_scan_service.GitHistorySource.has_new_entries",
                                                return_value=True,
                                            ):
                                                with patch(
                                                    "app.repo_analysis.services.incremental_scan_service.AnalysisService.start_scan",
                                                    AsyncMock(),
                                                ):
                                                    await IncrementalScanService.run_once()
                                                    start_analyze.assert_awaited_once_with(
                                                        "r5",
                                                        after_sha="abc123",
                                                        limit=settings.mr_experience_max_collect_per_run,
                                                    )

        asyncio.run(_run())

    def test_run_once_triggers_experience_analyze_first_time(self, monkeypatch, tmp_path: Path):
        """首次（last_collected_commit_sha 为空）：走 since 回看路径。"""
        repo = GitRepository(
            id="r5b",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )
        (tmp_path / "main.py").write_text("print('x')\n", encoding="utf-8")

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [repo]))
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch.object(IncrementalScanService, "_is_scan_active", AsyncMock(return_value=False)):
                    with patch.object(IncrementalScanService, "_needs_rescan", AsyncMock(return_value=False)):
                        with patch.object(IncrementalScanService, "_get_last_collected_sha", AsyncMock(return_value=None)):
                            with patch.object(IncrementalScanService, "_recover_stale_running", AsyncMock(return_value=0)):
                                with patch.object(IncrementalScanService, "_nudge_file_workers", AsyncMock()):
                                    with patch(
                                        "app.repo_analysis.services.incremental_scan_service.ExperienceService.is_job_running",
                                        AsyncMock(return_value=False),
                                    ):
                                        start_analyze = AsyncMock()
                                        with patch(
                                            "app.repo_analysis.services.incremental_scan_service.ExperienceService.start_analyze",
                                            start_analyze,
                                        ):
                                            with patch(
                                                "app.repo_analysis.services.incremental_scan_service.AnalysisService.start_scan",
                                                AsyncMock(),
                                            ):
                                                await IncrementalScanService.run_once()
                                                assert start_analyze.await_count == 1
                                                call_kwargs = start_analyze.call_args
                                                assert call_kwargs.args == ("r5b",)
                                                assert call_kwargs.kwargs["limit"] == settings.mr_experience_max_collect_per_run
                                                assert call_kwargs.kwargs.get("after_sha") is None
                                                # since 应为今天减去 lookback_days
                                                expected_since = (datetime.now() - timedelta(days=settings.mr_experience_lookback_days)).date().isoformat()
                                                assert call_kwargs.kwargs["since"] == expected_since

        asyncio.run(_run())

    def test_needs_experience_rescan_uses_last_collected_sha(self, monkeypatch, tmp_path: Path):
        repo = GitRepository(
            id="r6",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                task_mock = MagicMock()
                task_mock.last_collected_commit_sha = "abc123"
                db = MagicMock()
                db.scalar = AsyncMock(return_value=task_mock)
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch(
                    "app.repo_analysis.services.incremental_scan_service.GitHistorySource.has_new_entries",
                    return_value=True,
                ) as has_new:
                    result = await IncrementalScanService._needs_experience_rescan(repo)
                    assert result is True
                    has_new.assert_called_once_with(str(tmp_path), after_sha="abc123")

        asyncio.run(_run())

    def test_needs_experience_rescan_first_time_returns_true(self, monkeypatch, tmp_path: Path):
        """首次（last_collected_commit_sha 为空）：_needs_experience_rescan 返回 True。"""
        repo = GitRepository(
            id="r6b",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(return_value=None)  # 无 task 记录
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                result = await IncrementalScanService._needs_experience_rescan(repo)
                assert result is True

        asyncio.run(_run())

    def test_skip_experience_when_mr_disabled(self, monkeypatch, tmp_path: Path):
        repo = GitRepository(
            id="r7",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.incremental_scan_service.settings.mr_experience_enabled",
            False,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [repo]))
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch.object(
                    IncrementalScanService,
                    "_is_scan_active",
                    AsyncMock(return_value=False),
                ):
                    with patch.object(
                        IncrementalScanService,
                        "_needs_rescan",
                        AsyncMock(return_value=False),
                    ):
                        with patch.object(
                            IncrementalScanService,
                            "_recover_stale_running",
                            AsyncMock(return_value=0),
                        ):
                            with patch.object(
                                IncrementalScanService,
                                "_nudge_file_workers",
                                AsyncMock(),
                            ):
                                start_analyze = AsyncMock()
                                with patch(
                                    "app.repo_analysis.services.incremental_scan_service.ExperienceService.start_analyze",
                                    start_analyze,
                                ):
                                    await IncrementalScanService.run_once()
                                    start_analyze.assert_not_awaited()

        asyncio.run(_run())

    def test_skip_experience_when_job_running(self, monkeypatch, tmp_path: Path):
        repo = GitRepository(
            id="r8",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.incremental_scan_service.settings.mr_experience_enabled",
            True,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [repo]))
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch.object(
                    IncrementalScanService,
                    "_is_scan_active",
                    AsyncMock(return_value=False),
                ):
                    with patch.object(
                        IncrementalScanService,
                        "_needs_rescan",
                        AsyncMock(return_value=False),
                    ):
                        with patch.object(
                            IncrementalScanService,
                            "_needs_experience_rescan",
                            AsyncMock(return_value=True),
                        ):
                            with patch.object(
                                IncrementalScanService,
                                "_recover_stale_running",
                                AsyncMock(return_value=0),
                            ):
                                with patch.object(
                                    IncrementalScanService,
                                    "_nudge_file_workers",
                                    AsyncMock(),
                                ):
                                    start_analyze = AsyncMock()
                                    with patch(
                                        "app.repo_analysis.services.incremental_scan_service.ExperienceService.is_job_running",
                                        AsyncMock(return_value=True),
                                    ):
                                        with patch(
                                            "app.repo_analysis.services.incremental_scan_service.ExperienceService.start_analyze",
                                            start_analyze,
                                        ):
                                            await IncrementalScanService.run_once()
                                            start_analyze.assert_not_awaited()

        asyncio.run(_run())

    def test_needs_experience_triggers_when_never_collected(self, tmp_path: Path):
        """首次（last_collected_commit_sha 为空）：_needs_experience_rescan 返回 True（自动触发）。"""
        repo = GitRepository(
            id="r9",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )

        async def _run():
            with patch.object(
                IncrementalScanService,
                "_get_last_collected_sha",
                AsyncMock(return_value=None),
            ):
                return await IncrementalScanService._needs_experience_rescan(repo)

        assert asyncio.run(_run()) is True


class TestRunOnceRepoPathFilter:
    """run_once(repo_path=...) 只扫指定仓；为空时扫全部。"""

    def _make_repo(self, tmp_path: Path, repo_id: str) -> GitRepository:
        repo_dir = tmp_path / repo_id
        repo_dir.mkdir()
        (repo_dir / "main.py").write_text("print('x')\n", encoding="utf-8")
        return GitRepository(id=repo_id, local_path=str(repo_dir), kind=RepoKind.CODE)

    def _patch_common(self, mock_cm, db, repo_or_repos, scalar_mode: bool):
        if scalar_mode:
            db.scalar = AsyncMock(return_value=repo_or_repos)
        else:
            db.scalars = AsyncMock(return_value=MagicMock(all=lambda: repo_or_repos))
        mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

    def test_run_once_with_repo_path_only_scans_matching_repo(self, tmp_path: Path):
        repo_a = self._make_repo(tmp_path, "ra")
        repo_b = self._make_repo(tmp_path, "rb")

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                self._patch_common(mock_cm, db, repo_a, scalar_mode=True)
                with patch.object(IncrementalScanService, "_recover_stale_running", AsyncMock()):
                    with patch.object(IncrementalScanService, "_nudge_file_workers", AsyncMock()):
                        with patch.object(IncrementalScanService, "_is_scan_active", AsyncMock(return_value=True)):
                            with patch.object(IncrementalScanService, "_needs_rescan", AsyncMock(return_value=False)):
                                with patch.object(IncrementalScanService, "_maybe_trigger_experience_analyze", AsyncMock()) as exp_trigger:
                                    with patch("app.repo_analysis.services.incremental_scan_service.AnalysisService.start_scan", AsyncMock()) as start_scan:
                                        await IncrementalScanService.run_once(repo_path=repo_a.local_path)
                                        # 只对 repo_a 触发经验分析，repo_b 不应被触及
                                        exp_trigger.assert_awaited_once_with(repo_a)
                                        start_scan.assert_not_awaited()

        asyncio.run(_run())

    def test_run_once_with_repo_path_no_match_does_nothing(self, tmp_path: Path):
        repo_a = self._make_repo(tmp_path, "ra")

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                # repo_path 不匹配任何已登记仓 -> db.scalar 返回 None
                self._patch_common(mock_cm, db, None, scalar_mode=True)
                with patch.object(IncrementalScanService, "_recover_stale_running", AsyncMock()) as recover:
                    with patch.object(IncrementalScanService, "_maybe_trigger_experience_analyze", AsyncMock()) as exp_trigger:
                        await IncrementalScanService.run_once(repo_path="/nonexistent/path")
                        recover.assert_not_awaited()
                        exp_trigger.assert_not_awaited()

        asyncio.run(_run())

    def test_run_once_without_repo_path_scans_all_repos(self, tmp_path: Path):
        repo_a = self._make_repo(tmp_path, "ra")
        repo_b = self._make_repo(tmp_path, "rb")

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                self._patch_common(mock_cm, db, [repo_a, repo_b], scalar_mode=False)
                with patch.object(IncrementalScanService, "_recover_stale_running", AsyncMock()):
                    with patch.object(IncrementalScanService, "_nudge_file_workers", AsyncMock()):
                        with patch.object(IncrementalScanService, "_is_scan_active", AsyncMock(return_value=True)):
                            with patch.object(IncrementalScanService, "_needs_rescan", AsyncMock(return_value=False)):
                                with patch.object(IncrementalScanService, "_maybe_trigger_experience_analyze", AsyncMock()) as exp_trigger:
                                    with patch("app.repo_analysis.services.incremental_scan_service.AnalysisService.start_scan", AsyncMock()):
                                        await IncrementalScanService.run_once()
                                        # 两个仓都被触发
                                        assert exp_trigger.await_count == 2
                                        called_repos = {call.args[0] for call in exp_trigger.await_args_list}
                                        assert called_repos == {repo_a, repo_b}

        asyncio.run(_run())
