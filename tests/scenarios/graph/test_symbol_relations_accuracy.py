"""图谱符号 callers / callees / file_summary 准确率场景。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.framework.ground_truth import (
    FILE_SUMMARY_CASES,
    SYMBOL_CALLEES_CASES,
    SYMBOL_CALLERS_CASES,
)
from tests.scenarios.framework.session_support import ScenarioSession


@pytest.mark.scenario
@pytest.mark.slow
@pytest.mark.requires_codegraph
class TestGraphSymbolCallersAccuracy(ScenarioSession):
    @pytest.mark.parametrize("case", SYMBOL_CALLERS_CASES, ids=lambda c: c.case_id)
    def test_callers_accuracy(self, case) -> None:
        async def _run():
            res = await self.query_callers(case.symbol, limit=case.limit)
            assert res.result, res.message
            hits = [it.get("file_path") for it in (res.content.get("callers") or [])]
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
class TestGraphSymbolCalleesAccuracy(ScenarioSession):
    @pytest.mark.parametrize("case", SYMBOL_CALLEES_CASES, ids=lambda c: c.case_id)
    def test_callees_accuracy(self, case) -> None:
        async def _run():
            res = await self.query_callees(case.symbol, limit=case.limit)
            assert res.result, res.message
            hits = [it.get("file_path") for it in (res.content.get("callees") or [])]
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
class TestGraphFileSummaryAccuracy(ScenarioSession):
    @pytest.mark.parametrize("case", FILE_SUMMARY_CASES, ids=lambda c: c.case_id)
    def test_file_summary_accuracy(self, case) -> None:
        async def _run():
            res = await self.query_file_summary(case.extra["file"])
            assert res.result, res.message
            files = (res.content.get("files") or {})
            summary = files.get(case.extra["file"]) or {}
            class_names = [c.get("name") for c in (summary.get("classes") or [])]
            score = AccuracyMetrics.evaluate(
                case.case_id,
                class_names,
                case.expected_paths,
                prefix=None,
            )
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
            )
            print(
                f"[case] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
                f"classes={class_names}"
            )

        self.run_async(_run())
