import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.config.settings import settings
from app.repo_analysis.services.codevector.exact_match import ExactMatchService
from app.repo_analysis.services.search_index_meta import SearchIndexMeta
from app.repo_analysis.services.search_service import SearchService


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
            top_k=5,
        )
        # 强符号命中：丢弃向量填充，只保留定义
        assert len(items) == 1
        assert items[0]["match_source"] == "exact"
        assert items[0]["symbol_name"] == "TriggerAlarm"

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
            top_k=5,
        )
        assert len(items) == 1
        assert items[0]["match_source"] == "exact"

    def test_strong_symbol_drops_path_and_caps(self):
        exact = [
            {
                "file_path": "app/agents/core/react.py",
                "symbol_name": "ReActAgent",
                "_score": 3.0,
                "exact_tier": "symbol",
            },
            {
                "file_path": "app/agents/plan/react_executor.py",
                "symbol_name": None,
                "_score": 1.25,
                "exact_tier": "path",
            },
        ]
        items = SearchService.fuse_related_items(
            exact_items=exact,
            symbol_docs=[{"file_path": "noise.py", "_score": 0.95}],
            top_k=10,
        )
        assert len(items) == 1
        assert items[0]["file_path"] == "app/agents/core/react.py"

    def test_path_only_keeps_ratio_trim(self):
        exact = [
            {
                "file_path": "app/utils/auth/jwt_validator.py",
                "_score": 1.3,
                "exact_tier": "path",
            },
            {
                "file_path": "app/utils/auth/jwt_middleware.py",
                "_score": 1.2,
                "exact_tier": "path",
            },
            {
                "file_path": "app/unrelated/foo.py",
                "_score": 0.2,
                "exact_tier": "path",
            },
        ]
        items = SearchService.fuse_related_items(
            exact_items=exact,
            symbol_docs=[],
            top_k=10,
        )
        paths = {it["file_path"] for it in items}
        assert "app/utils/auth/jwt_validator.py" in paths
        assert "app/unrelated/foo.py" not in paths

    def test_symbol_summary_ranks_before_codegraph(self):
        items = SearchService.fuse_related_items(
            exact_items=[],
            symbol_docs=[
                {
                    "file_path": "app/agents/memorys/default/memory.py",
                    "_score": 0.55,
                }
            ],
            extra_items=[
                {
                    "file_path": "app/agents/core/subagent.py",
                    "score": 1.0,
                    "match_source": "codegraph",
                }
            ],
            top_k=5,
            keywords=["memory", "long-term memory"],
        )
        assert items
        assert items[0]["file_path"] == "app/agents/memorys/default/memory.py"
        assert items[0]["match_source"] == "symbol_summary"

    def test_weak_trim_shortens_without_strong_exact(self):
        docs = [{"file_path": f"pkg/f{i}.py", "_score": 0.9 - i * 0.02} for i in range(12)]
        items = SearchService.fuse_related_items(
            exact_items=[],
            symbol_docs=docs,
            top_k=15,
            keywords=["memory"],
        )
        assert 1 <= len(items) <= SearchService.RELATED_WEAK_CAP

    def test_weak_layers_put_overflow_in_also_consider(self):
        docs = [{"file_path": f"pkg/f{i}.py", "_score": 0.9 - i * 0.02} for i in range(12)]
        primary, also = SearchService.fuse_related_layers(
            exact_items=[],
            symbol_docs=docs,
            top_k=15,
            keywords=["memory"],
        )
        assert 1 <= len(primary) <= SearchService.RELATED_WEAK_CAP
        assert also
        primary_paths = {it["file_path"] for it in primary}
        also_paths = {it["file_path"] for it in also}
        assert primary_paths.isdisjoint(also_paths)
        assert len(also) <= SearchService.RELATED_ALSO_CONSIDER_CAP

    def test_strong_layers_short_primary_keeps_also(self):
        exact = [
            {
                "file_path": f"app/svc/a{i}.py",
                "symbol_name": "Foo",
                "symbol_kind": "class",
                "_score": 3.0 - i * 0.01,
                "exact_tier": "symbol",
            }
            for i in range(6)
        ]
        primary, also = SearchService.fuse_related_layers(
            exact_items=exact,
            symbol_docs=[],
            top_k=10,
            keywords=["Foo"],
        )
        assert 1 <= len(primary) <= SearchService.STRONG_SYMBOL_CAP
        assert also
        assert len(primary) + len(also) <= 6


class TestRelatedChannelFlags:
    def test_channel_flags_default_excludes_graph(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_symbol_summary_enabled", True)
        monkeypatch.setattr(settings, "code_graph_enabled", True)
        monkeypatch.setattr(settings, "code_analysis_related_include_graph", False)
        flags = SearchService.related_channel_flags()
        assert flags == {"symbol": True, "codegraph": False}

    def test_channel_flags_can_opt_in_graph(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_symbol_summary_enabled", True)
        monkeypatch.setattr(settings, "code_graph_enabled", True)
        monkeypatch.setattr(settings, "code_analysis_related_include_graph", True)
        flags = SearchService.related_channel_flags()
        assert flags == {"symbol": True, "codegraph": True}

    def test_capability_flags(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_line_chunk_enabled", False)
        monkeypatch.setattr(settings, "code_analysis_symbol_summary_enabled", True)
        monkeypatch.setattr(settings, "code_graph_enabled", True)
        monkeypatch.setattr(settings, "mr_experience_enabled", False)
        assert SearchService.capability_flags() == {
            "chunk": False,
            "symbol": True,
            "codegraph": True,
            "mr_experience": False,
        }


class TestExactScoring:
    def test_symbol_full_name_beats_weak_path(self):
        assert ExactMatchService.score_symbol_keyword("ReActAgent", "ReActAgent", "app/agents/core/react.py") >= 2.5
        assert ExactMatchService.score_symbol_keyword("agent", "BaseAgent", "app/agents/core/base.py") == 0.0
        assert ExactMatchService.score_symbol_keyword("AgentState", "AgentState", "app/agents/core/base.py") >= 2.5

    def test_symbol_ignores_path_only_rows(self):
        # 引用文件：符号名不匹配时不应靠路径得分为 exact
        assert ExactMatchService.score_symbol_keyword("ReActAgent", "run_react", "app/agents/plan/react_executor.py") == 0.0
        assert ExactMatchService.score_symbol_keyword("ReActAgent", "helper", "app/agents/core/react.py") == 0.0

    def test_path_rejects_short_and_weak_terms(self):
        assert ExactMatchService.score_path_keyword("agent", "app/agents/core/base.py") == 0.0
        assert ExactMatchService.score_path_keyword("core", "app/agents/core/base.py") == 0.0
        assert ExactMatchService.score_path_keyword("jwt_validator", "app/utils/auth/jwt_validator.py") >= 1.2
        assert ExactMatchService.score_path_keyword("agents/core/base", "app/agents/core/base.py") >= 1.3


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

    def test_similar_rejects_when_chunk_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_line_chunk_enabled", False)

        async def _run():
            with pytest.raises(ValueError, match="LINE_CHUNK"):
                await SearchService.search_similar_code("r1", "def foo():\n  pass")

        asyncio.run(_run())

    def test_patterns_rejects_when_experience_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "mr_experience_enabled", False)

        async def _run():
            with pytest.raises(ValueError, match="MR_EXPERIENCE"):
                await SearchService.search_patterns("r1", "改告警")

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
