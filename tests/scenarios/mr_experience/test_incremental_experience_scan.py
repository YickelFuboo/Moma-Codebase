"""MR 经验增量扫描功能场景：相对上次已分析 MR 检测新 merge 并触发 analyze。"""
from __future__ import annotations
import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.repo_analysis.services.incremental_scan_service import IncrementalScanService
from app.repo_analysis.services.mr_experience.git_history_source import GitHistorySource
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


pytestmark = pytest.mark.scenario


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return (completed.stdout or "").strip()


def _create_repo_with_merge(repo: Path) -> str:
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "checkout", "-b", "main")
    f = repo / "svc.py"
    f.write_text("def run():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "svc.py")
    _git(repo, "commit", "-m", "init")
    _git(repo, "checkout", "-b", "feat-a")
    f.write_text("def run():\n    return 2\n", encoding="utf-8")
    _git(repo, "add", "svc.py")
    _git(repo, "commit", "-m", "feat a")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "-m", "Merge feat-a", "feat-a")
    return _git(repo, "rev-parse", "HEAD")


def _add_second_merge(repo: Path) -> str:
    _git(repo, "checkout", "-b", "feat-b")
    f = repo / "svc.py"
    f.write_text("def run():\n    return 3\n", encoding="utf-8")
    _git(repo, "add", "svc.py")
    _git(repo, "commit", "-m", "feat b")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "-m", "Merge feat-b", "feat-b")
    return _git(repo, "rev-parse", "HEAD")


class TestIncrementalExperienceScanScenario:
    def test_has_new_merge_after_last_analyzed_sha(self, tmp_path: Path):
        repo = tmp_path / "merge_repo"
        repo.mkdir()
        first_merge_sha = _create_repo_with_merge(repo)

        assert GitHistorySource.has_new_entries(str(repo), after_sha=None) is True
        assert GitHistorySource.has_new_entries(str(repo), after_sha=first_merge_sha) is False

        _add_second_merge(repo)
        assert GitHistorySource.has_new_entries(str(repo), after_sha=first_merge_sha) is True

    def test_needs_experience_rescan_with_real_git_history(self, tmp_path: Path):
        repo_dir = tmp_path / "merge_repo2"
        repo_dir.mkdir()
        first_merge_sha = _create_repo_with_merge(repo_dir)
        git_repo = GitRepository(
            id="exp-inc-1",
            local_path=str(repo_dir),
            kind=RepoKind.CODE,
        )

        async def _run(after_sha):
            with patch(
                "app.repo_analysis.services.experience_service.get_db_session"
            ) as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(return_value=after_sha)
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await IncrementalScanService._needs_experience_rescan(git_repo)

        assert asyncio.run(_run(first_merge_sha)) is False
        _add_second_merge(repo_dir)
        assert asyncio.run(_run(first_merge_sha)) is True

    def test_run_once_triggers_analyze_when_new_merge_detected(self, tmp_path: Path, monkeypatch):
        repo_dir = tmp_path / "merge_repo3"
        repo_dir.mkdir()
        first_merge_sha = _create_repo_with_merge(repo_dir)
        _add_second_merge(repo_dir)
        git_repo = GitRepository(
            id="exp-inc-2",
            local_path=str(repo_dir),
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
                db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [git_repo]))
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
                        with patch(
                            "app.repo_analysis.services.experience_service.get_db_session"
                        ) as exp_cm:
                            exp_db = MagicMock()
                            exp_db.scalar = AsyncMock(return_value=first_merge_sha)
                            exp_cm.return_value.__aenter__ = AsyncMock(return_value=exp_db)
                            exp_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                            start_analyze = AsyncMock()
                            with patch(
                                "app.repo_analysis.services.incremental_scan_service.ExperienceService.start_analyze",
                                start_analyze,
                            ):
                                with patch(
                                    "app.repo_analysis.services.incremental_scan_service.ExperienceService.is_job_running",
                                    AsyncMock(return_value=False),
                                ):
                                    await IncrementalScanService.run_once()
                                    start_analyze.assert_awaited_once_with(
                                        "exp-inc-2",
                                        limit=50,
                                    )

        asyncio.run(_run())

    def test_run_once_skips_lib_repo_for_experience(self, tmp_path: Path, monkeypatch):
        repo_dir = tmp_path / "lib_repo"
        repo_dir.mkdir()
        (repo_dir / "api.py").write_text("def api(): pass\n", encoding="utf-8")
        git_repo = GitRepository(
            id="exp-inc-lib",
            local_path=str(repo_dir),
            kind=RepoKind.LIB,
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
                db.scalars = AsyncMock(return_value=MagicMock(all=lambda: [git_repo]))
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
                        start_analyze = AsyncMock()
                        with patch(
                            "app.repo_analysis.services.incremental_scan_service.ExperienceService.start_analyze",
                            start_analyze,
                        ):
                            await IncrementalScanService.run_once()
                            start_analyze.assert_not_awaited()

        asyncio.run(_run())
