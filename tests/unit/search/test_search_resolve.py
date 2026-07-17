import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from app.repo_analysis.services.search_resolve.intent import SearchIntent, SearchIntentRouter
from app.repo_analysis.services.search_resolve.resolve_service import SearchResolveService


class TestSearchIntentRouter:
    def test_normalize_aliases(self):
        assert SearchIntentRouter.normalize_intent("locate") == SearchIntent.RELATED
        assert SearchIntentRouter.normalize_intent("experience") == SearchIntent.PATTERN
        assert SearchIntentRouter.normalize_intent(None) == SearchIntent.AUTO

    def test_normalize_rejects_unknown(self):
        with pytest.raises(ValueError, match="不支持的 intent"):
            SearchIntentRouter.normalize_intent("foo")

    def test_detect_similar_for_code_snippet(self):
        plan = SearchIntentRouter.plan(
            "async def think_and_act(self, q):\n    return await self.think(q)\n",
            repo_kind="code",
        )
        assert plan.intent == SearchIntent.SIMILAR
        assert plan.channels == ["similar"]

    def test_detect_pattern_for_experience_query(self):
        plan = SearchIntentRouter.plan("怎么改告警名称的历史经验", repo_kind="code")
        assert plan.intent == SearchIntent.PATTERN
        assert "pattern" in plan.channels
        assert "related" in plan.channels

    def test_detect_related_default(self):
        plan = SearchIntentRouter.plan("ReActAgent ContextBuilder", repo_kind="code")
        assert plan.intent == SearchIntent.RELATED
        assert plan.channels == ["related"]
        assert "ReActAgent" in plan.keywords

    def test_lib_defaults_to_api(self):
        plan = SearchIntentRouter.plan("读取文本文件", repo_kind="lib")
        assert plan.intent == SearchIntent.API
        assert plan.channels == ["api"]

    def test_code_rejects_api_intent(self):
        with pytest.raises(ValueError, match="不支持 intent=api"):
            SearchIntentRouter.plan("接口", repo_kind="code", intent_override="api")

    def test_lib_rejects_pattern_intent(self):
        with pytest.raises(ValueError, match="kind=lib"):
            SearchIntentRouter.plan("经验", repo_kind="lib", intent_override="pattern")

    def test_graph_fallback_without_target(self):
        plan = SearchIntentRouter.plan("谁依赖这个模块", repo_kind="code")
        assert plan.intent == SearchIntent.RELATED
        assert plan.fallback_from == "graph"

    def test_graph_extracts_file(self):
        plan = SearchIntentRouter.plan(
            "谁依赖 app/repo_analysis/services/search_service.py",
            repo_kind="code",
            intent_override="graph",
        )
        assert plan.intent == SearchIntent.GRAPH
        assert plan.graph_file.endswith("search_service.py")
        assert plan.graph_mode == "dependents"

    def test_chinese_keywords_extracted(self):
        plan = SearchIntentRouter.plan(
            "查找默认记忆提取提示词相关实现",
            repo_kind="code",
        )
        assert plan.intent == SearchIntent.RELATED
        joined = " ".join(plan.keywords)
        assert "记忆" in joined or "提示词" in joined or "默认记忆" in joined or any(
            "记忆" in k for k in plan.keywords
        )


class TestSearchResolveService:
    def test_resolve_related_channel(self, monkeypatch):
        class _Repo:
            id = "r1"
            kind = "code"

        class _CM:
            async def __aenter__(self):
                db = AsyncMock()
                db.scalar = AsyncMock(return_value=_Repo())
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.search_resolve.resolve_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.search_resolve.resolve_service.SearchIndexMeta.for_repo",
            AsyncMock(return_value={"scan_status": "completed"}),
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_related_files",
                AsyncMock(
                    return_value={
                        "total": 1,
                        "items": [
                            {
                                "file_path": "a.py",
                                "score": 1.2,
                                "match_source": "exact",
                            }
                        ],
                    }
                ),
            ):
                return await SearchResolveService.resolve(
                    "r1",
                    "ReActAgent",
                    intent="related",
                    top_k=5,
                )

        result = asyncio.run(_run())
        assert result["intent"] == "related"
        assert result["channels_used"] == ["related"]
        assert result["items"][0]["file_path"] == "a.py"
        assert "related" in result["sections"]

    def test_resolve_channel_failure_degrades(self, monkeypatch):
        class _Repo:
            id = "r1"
            kind = "code"

        class _CM:
            async def __aenter__(self):
                db = AsyncMock()
                db.scalar = AsyncMock(return_value=_Repo())
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.search_resolve.resolve_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.search_resolve.resolve_service.SearchIndexMeta.for_repo",
            AsyncMock(return_value={}),
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_patterns",
                AsyncMock(side_effect=ValueError("no experience")),
            ):
                with patch(
                    "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_related_files",
                    AsyncMock(
                        return_value={
                            "total": 1,
                            "items": [{"file_path": "b.py", "score": 0.8, "match_source": "symbol_summary"}],
                        }
                    ),
                ):
                    return await SearchResolveService.resolve(
                        "r1",
                        "怎么改告警",
                        intent="pattern",
                        top_k=5,
                    )

        result = asyncio.run(_run())
        assert "pattern" in (result.get("channel_errors") or {})
        assert result["channels_used"] == ["related"]
        assert result["items"][0]["file_path"] == "b.py"

    def test_fuse_expands_pattern_relevant_files(self):
        items = [
            {
                "title": "Skills Hub",
                "match_source": "mr_experience",
                "channel": "pattern",
                "similarity": 0.9,
                "relevant_files": ["app/skills/hub/service.py", "app/ui/SkillsHubPanel.vue"],
            },
            {
                "file_path": "app/skills/hub/service.py",
                "score": 1.5,
                "match_source": "exact",
                "channel": "related",
            },
        ]
        expanded = []
        for it in items:
            expanded.append(it)
            if it.get("channel") == "pattern":
                expanded.extend(SearchResolveService._expand_pattern_file_hits(it))
        fused = SearchResolveService._fuse_items(expanded, top_k=5)
        paths = [str(it.get("file_path") or "") for it in fused]
        assert "app/skills/hub/service.py" in paths
        # exact 应优先于 pattern 展开
        top_file = next(it for it in fused if it.get("file_path") == "app/skills/hub/service.py")
        assert top_file.get("match_source") == "exact"
        assert any(it.get("file_path") == "app/ui/SkillsHubPanel.vue" for it in fused)

    def test_resolve_pattern_channel_expands_files(self, monkeypatch):
        """端到端：pattern 通道可达，且 relevant_files 展开进融合结果。"""

        class _Repo:
            id = "r1"
            kind = "code"

        class _CM:
            async def __aenter__(self):
                db = AsyncMock()
                db.scalar = AsyncMock(return_value=_Repo())
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.search_resolve.resolve_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.search_resolve.resolve_service.SearchIndexMeta.for_repo",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.search_resolve.resolve_service.settings.mr_experience_enabled",
            True,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_patterns",
                AsyncMock(
                    return_value={
                        "total": 1,
                        "items": [
                            {
                                "title": "Skills Hub",
                                "similarity": 0.91,
                                "quality_score": 0.8,
                                "relevant_files": ["app/skills/hub/service.py"],
                            }
                        ],
                    }
                ),
            ):
                with patch(
                    "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_related_files",
                    AsyncMock(return_value={"total": 0, "items": []}),
                ):
                    return await SearchResolveService.resolve(
                        "r1",
                        "Skill Hub 怎么改",
                        intent="pattern",
                        top_k=5,
                    )

        result = asyncio.run(_run())
        assert "pattern" not in (result.get("channel_errors") or {})
        assert "pattern" in (result.get("channels_used") or [])
        paths = [str(it.get("file_path") or "") for it in (result.get("items") or [])]
        titles = [str(it.get("title") or "") for it in (result.get("items") or [])]
        assert "app/skills/hub/service.py" in paths
        assert "Skills Hub" in titles
