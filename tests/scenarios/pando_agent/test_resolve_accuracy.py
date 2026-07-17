"""Pando-Agent：search resolve 真仓场景（intent + Top1）。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.framework.case_spec import PathSetCase
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


PANDO_RESOLVE_CASES = [
    PathSetCase(
        case_id="pando.resolve.related.ReActAgent",
        description="中文+符号：resolve 应走 related 并命中 react.py",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "查找 ReActAgent 实现位置",
            "expect_intent": "related",
            "expect_channel": "related",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.similar.think_and_act",
        description="代码片段：resolve 应走 similar 并命中 react.py",
        expected_paths=["app/agents/core/react.py"],
        min_precision=0.5,
        min_recall=1.0,
        top_k=3,
        extra={
            "query": (
                "async def think_and_act(self, question, run_ctx):\n"
                "    if self.tool_choices == ToolChoice.NONE:\n"
                "        content, usage = await self.think_only(question)\n"
                "        return content, [], usage, None\n"
            ),
            "expect_intent": "similar",
            "expect_channel": "similar",
        },
    ),
    PathSetCase(
        case_id="pando.resolve.related.ContextBuilder",
        description="符号定位：ContextBuilder",
        expected_paths=["app/agents/context/context.py"],
        min_precision=0.4,
        min_recall=1.0,
        top_k=5,
        extra={
            "query": "ContextBuilder",
            "expect_intent": "related",
            "expect_channel": "related",
        },
    ),
]


class TestPandoResolveAccuracy(PandoAgentScenarioSession):
    @pytest.mark.parametrize("case", PANDO_RESOLVE_CASES, ids=lambda c: c.case_id)
    def test_resolve_accuracy(self, case) -> None:
        self.require_repo_or_skip()

        async def _run():
            from app.repo_analysis.services.search_resolve import SearchResolveService

            await self.ensure_vector_ready()
            repo_id = await self.ensure_repo()
            result = await SearchResolveService.resolve(
                repo_id,
                case.extra["query"],
                top_k=case.top_k,
                intent="auto",
            )
            expect_intent = case.extra.get("expect_intent")
            if expect_intent:
                assert result.get("intent") == expect_intent, result.get("intent_reason")
            expect_channel = case.extra.get("expect_channel")
            if expect_channel:
                assert expect_channel in (result.get("channels_used") or [])
            items = result.get("items") or []
            hits = [it.get("file_path") for it in items if it.get("file_path")]
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
                require_precision=True,
            )
            top = hits[0] if hits else None
            print(
                f"[pando-resolve] {case.case_id} intent={result.get('intent')} "
                f"channels={result.get('channels_used')} P={score.precision:.2%} "
                f"R={score.recall:.2%} top={top}",
                flush=True,
            )

        self.run_async(_run())
