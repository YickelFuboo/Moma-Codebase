"""Pando-Agent：search resolve 真仓场景（intent + Top1）。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_RESOLVE_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


class TestPandoResolveAccuracy(PandoAgentScenarioSession):
    @pytest.mark.parametrize("case", PANDO_RESOLVE_CASES, ids=lambda c: c.case_id)
    def test_resolve_accuracy(self, case) -> None:
        self.require_repo_or_skip()

        async def _run():
            from app.repo_analysis.services.search_resolve import SearchResolveService
            from app.repo_analysis.services.search_service import SearchService

            await self.ensure_vector_ready()
            repo_id = await self.ensure_repo()
            result = await SearchResolveService.resolve(
                repo_id,
                case.extra["query"],
                top_k=case.top_k,
                intent="auto",
            )
            related_flags = SearchService.related_channel_flags()
            related_locate_on = bool(related_flags.get("symbol") or related_flags.get("codegraph"))
            expect_intent = case.extra.get("expect_intent")
            if expect_intent:
                assert result.get("intent") == expect_intent, result.get("intent_reason")
            expect_channel = case.extra.get("expect_channel")
            if expect_channel == "related" and not related_locate_on:
                used = set(result.get("channels_used") or [])
                assert used.intersection({"similar", "grep"}), (
                    f"符号摘要关闭后应仍有 similar/grep，实际 {sorted(used)} errors={result.get('channel_errors')}"
                )
            elif expect_channel:
                assert expect_channel in (result.get("channels_used") or [])
            expect_channels_any = case.extra.get("expect_channels_any") or []
            if expect_channels_any:
                used = set(result.get("channels_used") or [])
                allowed = set(expect_channels_any)
                if not related_locate_on:
                    allowed.discard("related")
                assert used.intersection(allowed or {"similar", "grep"}), (
                    f"期望通道之一 {sorted(allowed or {'similar', 'grep'})}，实际 {sorted(used)}"
                )
            if case.extra.get("expect_intent") == "related" and "nl" in case.case_id:
                used = result.get("channels_used") or []
                if related_locate_on:
                    assert "related" in used
                    assert len(used) >= 2, f"NL resolve 应并联多通道，实际={used}"
                else:
                    assert used, f"符号摘要关闭后 NL resolve 仍应有通道产出，实际={used}"
                    assert len(used) >= 1
            items = result.get("items") or []
            also = result.get("also_consider") or []
            hits = [it.get("file_path") for it in items if it.get("file_path")]
            also_hits = [it.get("file_path") for it in also if it.get("file_path")]
            union_hits = hits + [p for p in also_hits if p not in hits]
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
            union_score = AccuracyMetrics.evaluate(
                f"{case.case_id}.union",
                union_hits,
                case.expected_paths,
            )
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
                require_precision=case.extra.get("require_precision", False),
            )
            top = hits[0] if hits else None
            if case.extra.get("expect_top1_in_expected") and top:
                assert any(
                    exp.replace("\\", "/") in str(top).replace("\\", "/")
                    for exp in case.expected_paths
                ), f"{case.case_id}: Top1={top} 不在 expected={case.expected_paths}"
            print(
                f"[pando-resolve] {case.case_id} intent={result.get('intent')} "
                f"channels={result.get('channels_used')} "
                f"itemsP={score.precision:.2%} itemsR={score.recall:.2%} "
                f"unionP={union_score.precision:.2%} unionR={union_score.recall:.2%} "
                f"n_items={len(hits)} n_also={len(also_hits)} top={top}",
                flush=True,
            )

        self.run_async(_run())
