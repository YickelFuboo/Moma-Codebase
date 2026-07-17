"""Pando-Agent：Graph callers 准确率 + unsupported 明示闭环。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_CALLERS_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


pytestmark = [
    pytest.mark.scenario,
    pytest.mark.slow,
    pytest.mark.requires_codegraph,
]


class TestPandoCallersAccuracy(PandoAgentScenarioSession):
    @pytest.mark.parametrize("case", PANDO_CALLERS_CASES, ids=lambda c: c.case_id)
    def test_callers_accuracy(self, case) -> None:
        self.require_repo_or_skip()

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
                f"[pando] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
                f"hits={score.hits} expect={case.expected_paths}",
                flush=True,
            )

        self.run_async(_run())


class TestPandoGraphUnsupportedMessaging(PandoAgentScenarioSession):
    def test_unsupported_extension_message(self) -> None:
        self.require_repo_or_skip()

        async def _run():
            res = await self.query_dependents("README.md")
            assert res.result, res.message
            assert "扩展名" in (res.message or "")
            assert not (res.content or {}).get("dependents")

        self.run_async(_run())

    def test_missing_symbol_message(self) -> None:
        self.require_repo_or_skip()

        async def _run():
            res = await self.query_callers("TotallyFakeSymbolXYZ", limit=5)
            assert res.result, res.message
            assert "未找到符号" in (res.message or "")
            assert (res.content or {}).get("callers") == []

        self.run_async(_run())

    def test_empty_symbol_message(self) -> None:
        self.require_repo_or_skip()

        async def _run():
            res = await self.query_callers("   ", limit=5)
            assert not res.result
            assert "为空" in (res.message or "")

        self.run_async(_run())
