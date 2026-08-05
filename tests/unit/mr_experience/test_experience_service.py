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


class TestProcessBatchLimit:
    """_process_pending_and_failed(max_items=...) 分批控制。"""

    def test_max_items_stops_after_limit(self, monkeypatch):
        from app.repo_analysis.services.experience_service import ExperienceService
        from app.repo_analysis.models.experience_status import (
            ExperienceItemStatus,
            MrExperienceItem,
        )

        # 模拟 5 个 PENDING 条目
        items = []
        for i in range(5):
            it = MagicMock()
            it.id = f"item-{i}"
            it.repo_id = "r1"
            it.status = ExperienceItemStatus.PENDING.value
            it.retry_count = 0
            items.append(it)

        # 计数器必须跨 _CM 实例共享：_process_pending_and_failed 每轮迭代开新 session
        shared = {"call_count": 0}

        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                def _scalar_side_effect(*args, **kwargs):
                    if shared["call_count"] < len(items):
                        ret = items[shared["call_count"]]
                        shared["call_count"] += 1
                        return ret
                    return None
                db.scalar = AsyncMock(side_effect=_scalar_side_effect)
                db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
                db.commit = AsyncMock()
                db.rollback = AsyncMock()
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.ExperienceService._process_one_item",
            AsyncMock(),
        )

        async def _run():
            await ExperienceService._process_pending_and_failed(
                "r1",
                include_failed=False,
                max_items=3,
            )

        asyncio.run(_run())
        # 只处理 3 个（max_items=3），不是全部 5 个
        assert ExperienceService._process_one_item.await_count == 3

    def test_no_max_items_processes_all(self, monkeypatch):
        from app.repo_analysis.services.experience_service import ExperienceService
        from app.repo_analysis.models.experience_status import (
            ExperienceItemStatus,
        )

        items = []
        for i in range(3):
            it = MagicMock()
            it.id = f"item-{i}"
            it.repo_id = "r1"
            it.status = ExperienceItemStatus.PENDING.value
            it.retry_count = 0
            items.append(it)

        # 跨 session 共享计数器，否则每轮新 _CM 都从 0 开始，永远返回 items[0] -> 死循环
        shared = {"call_count": 0}

        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                def _scalar_side_effect(*args, **kwargs):
                    if shared["call_count"] < len(items):
                        ret = items[shared["call_count"]]
                        shared["call_count"] += 1
                        return ret
                    return None
                db.scalar = AsyncMock(side_effect=_scalar_side_effect)
                db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
                db.commit = AsyncMock()
                db.rollback = AsyncMock()
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.ExperienceService._process_one_item",
            AsyncMock(),
        )

        async def _run():
            await ExperienceService._process_pending_and_failed(
                "r1",
                include_failed=False,
                max_items=None,
            )

        asyncio.run(_run())
        # max_items=None 时处理全部 3 个
        assert ExperienceService._process_one_item.await_count == 3


class TestStartAnalyzeHighWaterMark:
    """start_analyze(after_sha=...) 收集后更新 RepoExperienceTask 高水位。"""

    def test_run_analyze_updates_last_collected_after_collection(self, monkeypatch):
        from app.repo_analysis.services.experience_service import ExperienceService
        from app.repo_analysis.services.mr_experience.git_history_source import GitHistorySource
        from app.repo_analysis.services.mr_experience.models import GitHistoryEntry

        # 模拟 git 收集返回 2 条 entry（newest 优先）
        entries = [
            GitHistoryEntry(
                commit_sha="sha-new",
                message="new merge",
                committed_at=None,
                is_merge=True,
            ),
            GitHistoryEntry(
                commit_sha="sha-old",
                message="old merge",
                committed_at=None,
                is_merge=True,
            ),
        ]
        monkeypatch.setattr(
            GitHistorySource,
            "collect",
            staticmethod(lambda *args, **kwargs: entries),
        )

        # 捕获 task 对象
        captured_task = MagicMock()
        captured_task.last_collected_commit_sha = None
        captured_task.last_collected_committed_at = None

        # _run_analyze 有两段独立 get_db_session：
        #   session 0: 写入 MrExperienceItem（每条 entry 调一次 db.scalar 查重）
        #   session 1: 更新高水位（调一次 db.scalar 取 task）
        # 用共享 session_idx 区分这两段，否则新 _CM 实例无法知道当前是哪一段
        shared = {"session_idx": 0}

        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                idx = shared["session_idx"]
                shared["session_idx"] += 1
                if idx == 0:
                    # 第 0 段：每条 entry 都不存在已存记录 -> 返回 None
                    db.scalar = AsyncMock(return_value=None)
                    db.add = MagicMock()
                else:
                    # 第 1 段：返回 captured_task 用于高水位更新
                    db.scalar = AsyncMock(return_value=captured_task)
                db.commit = AsyncMock()
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.ExperienceService._process_pending_and_failed",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.experience_service.ExperienceService._refresh_counters",
            AsyncMock(),
        )

        async def _run():
            await ExperienceService._run_analyze(
                "r1",
                "/x",
                since=None,
                after_sha="sha-prev",
                limit=50,
            )

        asyncio.run(_run())
        # 高水位应更新为 entries[0]（newest）
        assert captured_task.last_collected_commit_sha == "sha-new"
