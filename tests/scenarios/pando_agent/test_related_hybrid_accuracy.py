"""Pando-Agent 真仓：related 混合检索 Precision/Recall + index 新鲜度。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_RELATED_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


class TestPandoRelatedHybridAccuracy(PandoAgentScenarioSession):
    @pytest.mark.parametrize("case", PANDO_RELATED_CASES, ids=lambda c: c.case_id)
    def test_related_accuracy(self, case) -> None:
        self.require_repo_or_skip()
        if not self.ENABLE_SYMBOL_SUMMARY:
            pytest.skip("related 混合准确率依赖符号摘要，ENABLE_SYMBOL_SUMMARY=False 时跳过")

        async def _run():
            await self.ensure_vector_ready()
            result = await self.search_related(case.extra["keywords"], top_k=case.top_k)
            assert "index" in result, f"缺少 index 新鲜度字段: {result.keys()}"
            index = result.get("index") or {}
            assert "last_scan_finished_at" in index
            assert "index_age_seconds" in index
            assert "scan_status" in index
            assert index.get("last_scan_finished_at"), "分析后应有 last_scan_finished_at"

            items = result.get("items") or []
            also = result.get("also_consider") or []
            hits = [it.get("file_path") for it in items]
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
                require_precision=False,
            )
            if case.extra.get("expect_exact"):
                top = items[0] if items else {}
                assert top.get("match_source") == "exact", (
                    f"{case.case_id}: 期望 exact 置顶，实际 top={top}"
                )
                assert any(
                    exp.replace("\\", "/") in str(top.get("file_path") or "").replace("\\", "/")
                    for exp in case.expected_paths
                ), f"{case.case_id}: exact 置顶路径不符 top={top}"
            print(
                f"[pando] {case.case_id} itemsP={score.precision:.2%} itemsR={score.recall:.2%} "
                f"unionP={union_score.precision:.2%} unionR={union_score.recall:.2%} "
                f"n_items={len(hits)} n_also={len(also_hits)} "
                f"top_source={((items[0] or {}).get('match_source') if items else None)} "
                f"hits={score.hits}",
                flush=True,
            )

        self.run_async(_run())
