"""KnowledegBase-Service：similar 强/弱难例准确率。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.knowledge_base.ground_truth import KB_SIMILAR_CASES, KB_SIMILAR_WEAK_CASES
from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


class TestKbSimilarAccuracy(KnowledgeBaseScenarioSession):
    @pytest.mark.parametrize("case", KB_SIMILAR_CASES, ids=lambda c: c.case_id)
    def test_similar_accuracy(self, case) -> None:
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
            )
            top = str(items[0].get("file_path") or "").replace("\\", "/") if items else ""
            expected = {p.replace("\\", "/") for p in case.expected_paths}
            assert top in expected, f"{case.case_id} Top1={top} not in {expected}"
            print(
                f"[kb-similar] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} top={top}",
                flush=True,
            )

        self.run_async(_run())


class TestKbSimilarWeakAccuracy(KnowledgeBaseScenarioSession):
    @pytest.mark.parametrize("case", KB_SIMILAR_WEAK_CASES, ids=lambda c: c.case_id)
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
            )
            top = str(items[0].get("file_path") or "").replace("\\", "/") if items else ""
            expected = {p.replace("\\", "/") for p in case.expected_paths}
            assert top in expected, f"{case.case_id} Top1={top} not in {expected}"
            print(
                f"[kb-similar-weak] {case.case_id} P={score.precision:.2%} "
                f"R={score.recall:.2%} top={top}",
                flush=True,
            )

        self.run_async(_run())
