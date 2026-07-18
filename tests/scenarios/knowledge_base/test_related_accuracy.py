"""KnowledegBase-Service：related 难例准确率。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.knowledge_base.ground_truth import KB_RELATED_CASES
from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


class TestKbRelatedAccuracy(KnowledgeBaseScenarioSession):
    @pytest.mark.parametrize("case", KB_RELATED_CASES, ids=lambda c: c.case_id)
    def test_related_accuracy(self, case) -> None:
        self.require_repo_or_skip()

        async def _run():
            await self.ensure_vector_ready()
            result = await self.search_related(case.extra["keywords"], top_k=case.top_k)
            items = result.get("items") or []
            hits = [it.get("file_path") for it in items]
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
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
            print(
                f"[kb-related] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
                f"top={hits[:3]}",
                flush=True,
            )

        self.run_async(_run())
