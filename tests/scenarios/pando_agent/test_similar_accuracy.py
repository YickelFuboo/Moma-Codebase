"""Pando-Agent 真仓：chunk similar 相似代码片段 Precision/Recall。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_SIMILAR_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


class TestPandoSimilarAccuracy(PandoAgentScenarioSession):
    @pytest.mark.parametrize("case", PANDO_SIMILAR_CASES, ids=lambda c: c.case_id)
    def test_similar_accuracy(self, case) -> None:
        self.require_repo_or_skip()

        async def _run():
            await self.ensure_vector_ready()
            result = await self.search_similar(case.extra["code"], top_k=case.top_k)
            assert "index" in result, f"缺少 index 字段: {result.keys()}"
            items = result.get("items") or []
            hits = [it.get("file_path") for it in items]
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
                require_precision=False,
            )
            top_src = (items[0].get("match_source") if items else None)
            print(
                f"[pando-similar] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
                f"top_source={top_src} hits={score.hits}",
                flush=True,
            )

        self.run_async(_run())
