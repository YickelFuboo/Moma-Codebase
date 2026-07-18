import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from app.repo_analysis.services.search_resolve.intent import SearchIntent, SearchIntentRouter
from app.repo_analysis.services.search_resolve.resolve_service import SearchResolveService
from app.repo_analysis.services.search_resolve.result_presenter import ResolveResultPresenter


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
        assert result["items"][0].get("why")
        assert "a.py" in str(result.get("summary") or "")
        assert result.get("fallback_used") is None
        assert len(result["items"]) <= 3
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
        assert all(it.get("why") for it in result["items"])

    def test_agent_items_capped_at_three(self, monkeypatch):
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
        many = [
            {"file_path": f"f{i}.py", "score": 3.0 - i * 0.01, "match_source": "exact"}
            for i in range(8)
        ]

        async def _run():
            with patch(
                "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_related_files",
                AsyncMock(return_value={"total": 8, "items": many}),
            ):
                return await SearchResolveService.resolve(
                    "r1",
                    "Foo",
                    intent="related",
                    top_k=10,
                )

        result = asyncio.run(_run())
        assert result["fused_total"] == 8
        assert result["total"] == 3
        assert len(result["items"]) == 3
        assert "推荐 3 条" in str(result.get("summary") or "")

    def test_weak_related_attaches_pattern_fallback(self, monkeypatch):
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
            "app.repo_analysis.services.search_resolve.weak_fallback.settings.mr_experience_enabled",
            True,
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_related_files",
                AsyncMock(
                    return_value={
                        "total": 1,
                        "items": [
                            {
                                "file_path": "weak.py",
                                "score": 0.4,
                                "match_source": "symbol_summary",
                            }
                        ],
                    }
                ),
            ):
                with patch(
                    "app.repo_analysis.services.search_resolve.resolve_service.SearchService.search_patterns",
                    AsyncMock(
                        return_value={
                            "total": 1,
                            "items": [
                                {
                                    "title": "弱相关经验",
                                    "similarity": 0.88,
                                    "relevant_files": ["app/fallback/hit.py"],
                                }
                            ],
                        }
                    ),
                ):
                    return await SearchResolveService.resolve(
                        "r1",
                        "某个模糊能力",
                        intent="related",
                        top_k=5,
                    )

        result = asyncio.run(_run())
        assert result.get("fallback_used") == "pattern"
        assert "pattern" in (result.get("channels_used") or [])
        assert any(it.get("fallback") for it in result["items"])
        assert result["items"][-1].get("fallback") is True
        assert "app/fallback/hit.py" in str(result["items"][-1].get("file_path") or "")
        assert "兜底" in str(result.get("summary") or "")

    def test_agent_items_keeps_fallback_slot(self):
        items = [
            {"file_path": f"w{i}.py", "score": 0.5, "match_source": "symbol_summary"}
            for i in range(5)
        ]
        items.append(
            {
                "file_path": "fb.py",
                "score": 0.3,
                "match_source": "mr_experience",
                "fallback": True,
                "channel": "pattern",
            }
        )
        out = ResolveResultPresenter.agent_items(items)
        assert len(out) == 3
        assert out[-1]["file_path"] == "fb.py"
        assert out[-1].get("fallback") is True

    def test_presenter_why_and_summary(self):
        why = ResolveResultPresenter.why_for(
            {
                "channel": "related",
                "match_source": "exact",
                "file_path": "a/b.py",
                "symbol_name": "Foo",
            }
        )
        assert "a/b.py#Foo" in why
        assert "精确命中" in why
        items = ResolveResultPresenter.annotate(
            [{"channel": "related", "match_source": "exact", "file_path": "a.py"}]
        )
        assert items[0]["why"]
        summary = ResolveResultPresenter.summary(
            intent="related",
            items=items,
            fused_total=5,
            fallback_used=None,
        )
        assert "融合池 5" in summary
