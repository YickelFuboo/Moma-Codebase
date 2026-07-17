"""Pando-Agent：非极强 similar 查询，观察返回条数与 P/R。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_SIMILAR_WEAK_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


class TestPandoSimilarWeakAccuracy(PandoAgentScenarioSession):
    @pytest.mark.parametrize("case", PANDO_SIMILAR_WEAK_CASES, ids=lambda c: c.case_id)
    def test_similar_weak_accuracy(self, case) -> None:
        self.require_repo_or_skip()

        async def _run():
            await self.ensure_vector_ready()
            result = await self.search_similar(case.extra["code"], top_k=case.top_k)
            items = result.get("items") or []
            hits = [it.get("file_path") for it in items]
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
                require_precision=True,
            )
            assert items, f"{case.case_id} 无结果"
            top = str(items[0].get("file_path") or "").replace("\\", "/")
            expected = {p.replace("\\", "/") for p in case.expected_paths}
            assert top in expected, f"{case.case_id} Top1={top} not in {expected}"
            print(
                f"[pando-similar-weak] {case.case_id} P={score.precision:.2%} "
                f"R={score.recall:.2%} n={len(items)} top={top} hits={score.hits}",
                flush=True,
            )

        self.run_async(_run())
