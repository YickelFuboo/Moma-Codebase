"""相关文件检索准确率场景（行切面关键词；默认关符号摘要）。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.framework.ground_truth import RELATED_CASES
from tests.scenarios.framework.session_support import ScenarioSession


@pytest.mark.scenario
@pytest.mark.slow
class TestVectorRelatedAccuracy(ScenarioSession):
    ENABLE_SYMBOL_SUMMARY = False
    ENABLE_CODE_GRAPH = True
    ANALYZE_TARGET = "app/repo_analysis"
    # 按目录名 related 先于 similar 收集：此处负责建索引
    CLEAR_BEFORE_ANALYZE = True
    ANALYZE_TIMEOUT_SEC = 420

    @pytest.mark.parametrize("case", RELATED_CASES, ids=lambda c: c.case_id)
    def test_related_accuracy(self, case) -> None:
        async def _run():
            await self.ensure_vector_ready()
            result = await self.search_related(case.extra["keywords"], top_k=case.top_k)
            hits = [it.get("file_path") for it in (result.get("items") or [])]
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
                require_precision=False,
            )
            print(
                f"[case] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
                f"hits={score.hits} expect={score.expected}",
                flush=True,
            )

        self.run_async(_run())
