"""图谱文件级 dependents / dependencies 准确率场景。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.framework.ground_truth import FILE_DEPENDENCIES_CASES, FILE_DEPENDENTS_CASES
from tests.scenarios.framework.session_support import ScenarioSession


@pytest.mark.scenario
@pytest.mark.slow
@pytest.mark.requires_codegraph
class TestGraphFileDependentsAccuracy(ScenarioSession):
    @pytest.mark.parametrize("case", FILE_DEPENDENTS_CASES, ids=lambda c: c.case_id)
    def test_dependents_accuracy(self, case) -> None:
        async def _run():
            res = await self.query_dependents(case.extra["file"])
            assert res.result, res.message
            hits = res.content.get("dependents") or []
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
            )
            print(
                f"[case] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
                f"hits={score.hit_count} expect={score.expected_count}"
            )

        self.run_async(_run())


@pytest.mark.scenario
@pytest.mark.slow
@pytest.mark.requires_codegraph
class TestGraphFileDependenciesAccuracy(ScenarioSession):
    @pytest.mark.parametrize("case", FILE_DEPENDENCIES_CASES, ids=lambda c: c.case_id)
    def test_dependencies_accuracy(self, case) -> None:
        async def _run():
            res = await self.query_dependencies(case.extra["file"])
            assert res.result, res.message
            hits = res.content.get("dependented") or []
            score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
            )
            print(
                f"[case] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
                f"hits={score.hit_count} expect={score.expected_count}"
            )

        self.run_async(_run())
