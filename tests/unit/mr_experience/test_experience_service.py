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
        from app.repo_analysis.services.mr_experience.models import ExperienceExtractionResult, ExperiencePattern

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
                return_value=ExperienceExtractionResult(
                    extractable=True,
                    patterns=[
                        ExperiencePattern(
                            title="改告警名称",
                            scenario="调整监控告警命名时",
                            plan=["修改 a.go 中告警定义"],
                            patterns=["告警名与指标名保持一致"],
                            anchors=["a.go"],
                            source_commits=["sha"],
                            commit_message="fix alert name",
                            quality_score=0.9,
                        )
                    ],
                )
            ),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternVectorService.upsert_patterns",
            AsyncMock(),
        )

        async def _run():
            await ExperienceService._process_one_item("i1")

        asyncio.run(_run())
        assert item.status == ExperienceItemStatus.READY.value
        assert "改告警名称" in item.title
        assert item.last_error is None

    def test_process_skip_marks_skipped(self, monkeypatch):
        from app.repo_analysis.services.experience_service import ExperienceService
        from app.repo_analysis.models.experience_status import ExperienceItemStatus
        from app.repo_analysis.services.mr_experience.models import ExperienceExtractionResult

        item = MagicMock()
        item.id = "i3"
        item.repo_id = "r1"
        item.commit_sha = "sha3"
        item.commit_message = "bump lock"
        item.candidate_files_json = '[{"path":"a.py","status":"M","additions":1,"deletions":0}]'
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
                return_value=ExperienceExtractionResult(
                    extractable=False,
                    skip_reason="纯格式化",
                )
            ),
        )
        upsert = AsyncMock()
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternVectorService.upsert_patterns",
            upsert,
        )

        async def _run():
            await ExperienceService._process_one_item("i3")

        asyncio.run(_run())
        assert item.status == ExperienceItemStatus.SKIPPED.value
        assert item.title is None
        upsert.assert_not_awaited()

    def test_process_low_quality_marks_skipped(self, monkeypatch):
        from app.repo_analysis.services.experience_service import ExperienceService
        from app.repo_analysis.models.experience_status import ExperienceItemStatus
        from app.repo_analysis.services.mr_experience.models import ExperienceExtractionResult, ExperiencePattern

        item = MagicMock()
        item.id = "i4"
        item.repo_id = "r1"
        item.commit_sha = "sha4"
        item.commit_message = "refactor"
        item.candidate_files_json = '[{"path":"a.py","status":"M","additions":10,"deletions":8}]'
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
            "app.repo_analysis.services.experience_service.settings.mr_experience_min_quality_score",
            0.8,
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternSummarizer.summarize",
            AsyncMock(
                return_value=ExperienceExtractionResult(
                    extractable=True,
                    patterns=[
                        ExperiencePattern(
                            title="弱经验",
                            scenario="弱场景",
                            plan=[],
                            patterns=["轻量重命名"],
                            anchors=[],
                            source_commits=["sha4"],
                            quality_score=0.4,
                        )
                    ],
                )
            ),
        )
        upsert = AsyncMock()
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.PatternVectorService.upsert_patterns",
            upsert,
        )

        async def _run():
            await ExperienceService._process_one_item("i4")

        asyncio.run(_run())
        assert item.status == ExperienceItemStatus.SKIPPED.value
        upsert.assert_not_awaited()

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
            "app.repo_analysis.services.experience_service.PatternVectorService.upsert_patterns",
            upsert,
        )

        async def _run():
            await ExperienceService._process_one_item("i2")

        asyncio.run(_run())
        assert item.status == ExperienceItemStatus.FAILED.value
        assert item.retry_count == 2
        assert "boom" in str(item.last_error)
        upsert.assert_not_awaited()
