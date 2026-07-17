import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.repo_analysis.models.experience_status import ExperienceJobStatus
from app.repo_analysis.services.experience_service import ExperienceService


class TestExperienceIncrementalHelpers:
    def test_is_job_running_when_task_in_memory(self):
        async def _run():
            loop = asyncio.get_running_loop()
            task = loop.create_future()
            ExperienceService._running_jobs["r1"] = task
            try:
                return await ExperienceService.is_job_running("r1")
            finally:
                ExperienceService._running_jobs.pop("r1", None)

        assert asyncio.run(_run()) is True

    def test_is_job_running_when_db_status_running(self):
        async def _run():
            with patch("app.repo_analysis.services.experience_service.get_db_session") as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(return_value=ExperienceJobStatus.RUNNING.value)
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await ExperienceService.is_job_running("r2")

        assert asyncio.run(_run()) is True

    def test_is_job_running_when_idle(self):
        async def _run():
            with patch("app.repo_analysis.services.experience_service.get_db_session") as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(return_value=ExperienceJobStatus.COMPLETED.value)
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await ExperienceService.is_job_running("r3")

        assert asyncio.run(_run()) is False

    def test_get_latest_analyzed_commit_sha_returns_none_when_empty(self):
        async def _run():
            with patch("app.repo_analysis.services.experience_service.get_db_session") as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(return_value=None)
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await ExperienceService.get_latest_analyzed_commit_sha("r4")

        assert asyncio.run(_run()) is None

    def test_get_latest_analyzed_commit_sha_returns_latest(self):
        async def _run():
            with patch("app.repo_analysis.services.experience_service.get_db_session") as mock_cm:
                db = MagicMock()
                db.scalar = AsyncMock(return_value="deadbeef")
                mock_cm.return_value.__aenter__ = AsyncMock(return_value=db)
                mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)
                return await ExperienceService.get_latest_analyzed_commit_sha("r5")

        assert asyncio.run(_run()) == "deadbeef"
