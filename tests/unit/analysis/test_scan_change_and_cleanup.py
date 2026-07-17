"""增量扫描：缺失清理 + git 判变 UT。"""
from __future__ import annotations
import asyncio
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.repo_analysis.models.analysis_status import RepoAnalysisTask
from app.repo_analysis.services.analysis_service import AnalysisService
from app.repo_analysis.services.incremental_scan_service import IncrementalScanService
from app.repo_analysis.services.scan_change_detector import ScanChangeDetector
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


def _git_init_with_file(root: Path, name: str = "a.py", content: str = "x=1\n") -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    f = root / name
    f.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )


class TestScanChangeDetector:
    def test_dirty_working_tree_needs_rescan(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "app.repo_analysis.services.scan_change_detector.settings.runtime_data_dir",
            str(tmp_path / "rt"),
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        _git_init_with_file(repo)
        ScanChangeDetector.save_git_head("r1", ScanChangeDetector.current_head(str(repo)))
        (repo / "b.py").write_text("y=2\n", encoding="utf-8")
        assert ScanChangeDetector.needs_rescan_by_git(
            "r1",
            str(repo),
            {".py"},
        ) is True

    def test_clean_same_head_skips_rescan(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "app.repo_analysis.services.scan_change_detector.settings.runtime_data_dir",
            str(tmp_path / "rt"),
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        _git_init_with_file(repo)
        head = ScanChangeDetector.current_head(str(repo))
        ScanChangeDetector.save_git_head("r2", head)
        assert ScanChangeDetector.needs_rescan_by_git(
            "r2",
            str(repo),
            {".py"},
        ) is False

    def test_head_moved_needs_rescan(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "app.repo_analysis.services.scan_change_detector.settings.runtime_data_dir",
            str(tmp_path / "rt"),
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        _git_init_with_file(repo)
        ScanChangeDetector.save_git_head("r3", "deadbeef")
        assert ScanChangeDetector.needs_rescan_by_git(
            "r3",
            str(repo),
            {".py"},
        ) is True

    def test_non_git_returns_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "app.repo_analysis.services.scan_change_detector.settings.runtime_data_dir",
            str(tmp_path / "rt"),
        )
        (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
        assert ScanChangeDetector.needs_rescan_by_git(
            "r4",
            str(tmp_path),
            {".py"},
        ) is None


class TestNeedsRescanGitPrefer:
    def test_git_clean_ignores_newer_mtime(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "app.repo_analysis.services.scan_change_detector.settings.runtime_data_dir",
            str(tmp_path / "rt"),
        )
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        _git_init_with_file(repo_dir)
        head = ScanChangeDetector.current_head(str(repo_dir))
        ScanChangeDetector.save_git_head("rg1", head)
        # 人为把文件 mtime 推到未来，mtime 策略会误触发；git 策略应跳过
        f = repo_dir / "a.py"
        future = datetime.now() + timedelta(hours=2)
        import os

        os.utime(f, (future.timestamp(), future.timestamp()))
        repo = GitRepository(id="rg1", local_path=str(repo_dir), kind=RepoKind.CODE)
        task = RepoAnalysisTask(
            repo_id="rg1",
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

        assert asyncio.run(_run()) is False


class TestDeleteMissingPurgesAnalysisData:
    def test_delete_missing_calls_full_cleanup(self, tmp_path: Path):
        async def _run():
            db = MagicMock()
            db.scalars = AsyncMock(
                return_value=MagicMock(all=lambda: ["gone.py", "keep.py"])
            )
            db.commit = AsyncMock()
            with patch(
                "app.repo_analysis.services.analysis_service.FileAnalysisService.delete_file_analysis_data",
                AsyncMock(return_value={}),
            ) as purge:
                await AnalysisService._delete_missing_files_in_cur_dir(
                    db=db,
                    repo_id="r9",
                    repo_root=str(tmp_path),
                    cur_dir=str(tmp_path),
                    existing_files={"keep.py"},
                )
                purge.assert_awaited_once_with(
                    repo_id="r9",
                    rel_file_path="gone.py",
                    force=True,
                )
                db.commit.assert_awaited()

        asyncio.run(_run())
