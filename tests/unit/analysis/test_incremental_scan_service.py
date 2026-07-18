import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
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
                                                start_analyze.assert_awaited_once_with(
                                                    "r5",
                                                    limit=50,
                                                )

        asyncio.run(_run())

    def test_needs_experience_rescan_uses_last_analyzed_sha(self, monkeypatch, tmp_path: Path):
        repo = GitRepository(
            id="r6",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.experience_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(return_value="abc123")
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

    def test_needs_experience_skips_when_never_analyzed(self, tmp_path: Path):
        repo = GitRepository(
            id="r9",
            local_path=str(tmp_path),
            kind=RepoKind.CODE,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.incremental_scan_service.ExperienceService.get_latest_analyzed_commit_sha",
                AsyncMock(return_value=None),
            ):
                return await IncrementalScanService._needs_experience_rescan(repo)

        assert asyncio.run(_run()) is False
