import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.cli.experience import experience
from click.testing import CliRunner
from app.repo_mgmt.models.git_repo_mgmt import RepoKind


class TestExperienceCliGuards:
    def test_lib_kind_rejected(self, monkeypatch):
        class _Repo:
            id = "r1"
            kind = RepoKind.LIB

        async def _get_repo(path):
            return _Repo()

        monkeypatch.setattr("app.cli.experience.get_repo_by_path", _get_repo)
        monkeypatch.setattr("app.cli.experience.run_async", lambda coro, scheduler=False: asyncio.get_event_loop().run_until_complete(coro) if False else None)

        # 直接测 start 路径里的 kind 判断：通过 ExperienceService
        from app.repo_analysis.services.experience_service import ExperienceService

        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo())
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            with pytest.raises(ValueError, match="kind=code"):
                await ExperienceService.start_analyze("r1")

        asyncio.run(_run())


class TestExperienceProcessOneItem:
    def test_process_success_marks_ready(self, monkeypatch):
        from app.repo_analysis.services.experience_service import ExperienceService
        from app.repo_analysis.models.experience_status import ExperienceItemStatus
        from app.repo_analysis.services.mr_experience.models import ExperiencePattern, ExperienceStep

        item = MagicMock()
        item.id = "i1"
        item.repo_id = "r1"
        item.commit_sha = "sha"
        item.commit_message = "fix alert name"
        item.candidate_files_json = '[{"path":"a.go","status":"M","additions":3,"deletions":1}]'
        item.status = ExperienceItemStatus.RUNNING.value
        item.title = None
        item.steps_json = None
        item.last_error = None

        class _CM:
            def __init__(self):
                self.db = MagicMock()
                self.db.scalar = AsyncMock(return_value=item)
                self.db.commit = AsyncMock()

            async def __aenter__(self):
                return self.db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternSummarizer.summarize",
            AsyncMock(
                return_value=ExperiencePattern(
                    title="改告警名称",
                    steps=[ExperienceStep(file="a.go", action="修改告警名称")],
                    source_commits=["sha"],
                    commit_message="fix alert name",
                )
            ),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternVectorService.upsert_pattern",
            AsyncMock(),
        )

        async def _run():
            await ExperienceService._process_one_item("i1")

        asyncio.run(_run())
        assert item.status == ExperienceItemStatus.READY.value
        assert item.title == "改告警名称"
        assert item.last_error is None

    def test_process_fail_marks_failed_increments_retry(self, monkeypatch):
        from app.repo_analysis.services.experience_service import ExperienceService
        from app.repo_analysis.models.experience_status import ExperienceItemStatus
        from app.repo_analysis.services.mr_experience.pattern_summarizer import PatternSummarizerError

        item = MagicMock()
        item.id = "i2"
        item.repo_id = "r1"
        item.commit_sha = "sha2"
        item.commit_message = "x"
        item.candidate_files_json = '[{"path":"a.py","status":"M","additions":1,"deletions":0}]'
        item.status = ExperienceItemStatus.RUNNING.value
        item.retry_count = 1
        item.last_error = None

        class _CM:
            def __init__(self):
                self.db = MagicMock()
                self.db.scalar = AsyncMock(return_value=item)
                self.db.commit = AsyncMock()

            async def __aenter__(self):
                return self.db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternSummarizer.summarize",
            AsyncMock(side_effect=PatternSummarizerError("boom")),
        )
        upsert = AsyncMock()
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternVectorService.upsert_pattern",
            upsert,
        )

        async def _run():
            await ExperienceService._process_one_item("i2")

        asyncio.run(_run())
        assert item.status == ExperienceItemStatus.FAILED.value
        assert item.retry_count == 2
        assert "boom" in str(item.last_error)
        upsert.assert_not_awaited()
