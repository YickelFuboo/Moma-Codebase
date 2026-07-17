import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.repo_analysis.services.codevector.exact_match import ExactMatchService
from app.repo_analysis.services.search_index_meta import SearchIndexMeta
from app.repo_analysis.services.search_service import SearchService


class TestExactScoring:
    def test_symbol_full_name_beats_weak_path(self):
        assert ExactMatchService.score_symbol_keyword("ReActAgent", "ReActAgent", "app/agents/core/react.py") >= 2.5
        assert ExactMatchService.score_symbol_keyword("agent", "BaseAgent", "app/agents/core/base.py") == 0.0
        assert ExactMatchService.score_symbol_keyword("AgentState", "AgentState", "app/agents/core/base.py") >= 2.5

    def test_path_rejects_short_and_weak_terms(self):
        assert ExactMatchService.score_path_keyword("agent", "app/agents/core/base.py") == 0.0
        assert ExactMatchService.score_path_keyword("core", "app/agents/core/base.py") == 0.0
        assert ExactMatchService.score_path_keyword("jwt_validator", "app/utils/auth/jwt_validator.py") >= 1.2
        assert ExactMatchService.score_path_keyword("agents/core/base", "app/agents/core/base.py") >= 1.3


class TestFuseRelatedItems:
    def test_exact_symbol_ranks_before_vector(self):
        exact = [
            {
                "file_path": "a.py",
                "symbol_kind": "function",
                "symbol_name": "TriggerAlarm",
                "start_line": 1,
                "end_line": 2,
                "_score": 3.0,
                "exact_tier": "symbol",
            }
        ]
        symbol_docs = [
            {
                "file_path": "b.py",
                "symbol_kind": "function",
                "symbol_name": "other",
                "start_line": 1,
                "end_line": 3,
                "_score": 0.99,
            }
        ]
        items = SearchService.fuse_related_items(
            exact_items=exact,
            symbol_docs=symbol_docs,
            chunk_docs=[],
            top_k=5,
        )
        assert items[0]["match_source"] == "exact"
        assert items[0]["symbol_name"] == "TriggerAlarm"
        assert items[1]["match_source"] == "symbol_summary"

    def test_dedupe_by_file_keeps_best(self):
        exact = [
            {
                "file_path": "a.py",
                "symbol_kind": "function",
                "symbol_name": "foo",
                "start_line": 1,
                "end_line": 2,
                "_score": 3.0,
                "exact_tier": "symbol",
            }
        ]
        symbol_docs = [
            {
                "file_path": "a.py",
                "symbol_kind": "function",
                "symbol_name": "foo",
                "start_line": 1,
                "end_line": 2,
                "_score": 0.9,
            },
            {
                "file_path": "a.py",
                "symbol_kind": None,
                "symbol_name": None,
                "start_line": 10,
                "end_line": 20,
                "_score": 0.8,
            },
        ]
        items = SearchService.fuse_related_items(
            exact_items=exact,
            symbol_docs=symbol_docs,
            chunk_docs=[],
            top_k=5,
        )
        assert len(items) == 1
        assert items[0]["match_source"] == "exact"


class TestExactMatchService:
    def test_match_symbols_by_name(self, monkeypatch):
        rows = [
            {
                "file_path": "svc/alarm.py",
                "symbol_kind": "function",
                "symbol_name": "TriggerAlarm",
                "start_line": 10,
                "end_line": 20,
                "summary": "触发告警",
            },
            {
                "file_path": "svc/other.py",
                "symbol_kind": "function",
                "symbol_name": "helper",
                "start_line": 1,
                "end_line": 2,
                "summary": "x",
            },
        ]
        monkeypatch.setattr(
            ExactMatchService,
            "_embedding_dim",
            staticmethod(AsyncMock(return_value=8)),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.codevector.exact_match.VECTOR_STORE_CONN.space_exists",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.codevector.exact_match.VECTOR_STORE_CONN.list_records",
            AsyncMock(return_value=rows),
        )

        async def _run():
            hits = await ExactMatchService.match_symbols("r1", ["TriggerAlarm"], top_k=5)
            assert len(hits) == 1
            assert hits[0]["symbol_name"] == "TriggerAlarm"
            assert hits[0]["match_source"] == "exact"
            assert hits[0]["exact_tier"] == "symbol"

        asyncio.run(_run())


class TestSearchIndexMeta:
    def test_age_seconds(self, monkeypatch):
        finished = datetime.now() - timedelta(seconds=120)

        class _Task:
            last_scan_finished_at = finished
            scan_status = "completed"

        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Task())
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.search_index_meta.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            meta = await SearchIndexMeta.for_repo("r1")
            assert meta["scan_status"] == "completed"
            assert meta["index_age_seconds"] is not None
            assert meta["index_age_seconds"] >= 100

        asyncio.run(_run())


class TestSearchChunksSymbolsGuards:
    def test_chunks_rejects_empty(self):
        async def _run():
            with pytest.raises(ValueError, match="query"):
                await SearchService.search_chunks("r1", "  ")

        asyncio.run(_run())

    def test_symbols_rejects_lib(self, monkeypatch):
        class _Repo:
            kind = "lib"
            id = "r1"

        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo())
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.search_service.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            with pytest.raises(ValueError, match="kind=code"):
                await SearchService.search_symbols("r1", "foo")

        asyncio.run(_run())
