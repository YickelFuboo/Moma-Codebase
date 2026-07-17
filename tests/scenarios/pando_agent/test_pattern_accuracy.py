"""Pando-Agent：search pattern 真仓标题集合准确率（Top1 + P/R）。"""
from __future__ import annotations
import pytest
from tests.scenarios.framework.accuracy import AccuracyMetrics, title_matches
from tests.scenarios.pando_agent.ground_truth import PANDO_PATTERN_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


pytestmark = [pytest.mark.scenario, pytest.mark.slow]


class TestPandoPatternAccuracy(PandoAgentScenarioSession):
    @pytest.mark.parametrize("case", PANDO_PATTERN_CASES, ids=lambda c: c.case_id)
    def test_pattern_accuracy(self, case) -> None:
        self.require_repo_or_skip()

        async def _run():
            from app.config.settings import settings
            from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService
            from app.repo_analysis.services.search_service import SearchService

            if not settings.mr_experience_enabled:
                pytest.skip("MR_EXPERIENCE_ENABLED 未开启")
            repo_id = await self.ensure_repo()
            if not await PatternVectorService.space_exists(repo_id):
                pytest.skip("该仓库尚无经验向量，请先 experience analyze")

            result = await SearchService.search_patterns(
                repo_id,
                case.extra["query"],
                top_k=case.top_k,
            )
            items = result.get("items") or []
            hits = [str(it.get("title") or "").strip() for it in items if it.get("title")]
            score = AccuracyMetrics.evaluate_titles(
                case.case_id,
                hits,
                case.expected_titles,
            )
            AccuracyMetrics.assert_pass(
                score,
                min_precision=case.min_precision,
                min_recall=case.min_recall,
                require_precision=True,
            )
            if case.extra.get("require_top1"):
                top = hits[0] if hits else ""
                primary = case.expected_titles[0]
                assert title_matches(top, primary), (
                    f"{case.case_id}: Top1 未命中期望标题子串; "
                    f"top={top!r} expected={primary!r} hits={hits}"
                )
            print(
                f"[pando-pattern] {case.case_id} P={score.precision:.2%} "
                f"R={score.recall:.2%} top={hits[0] if hits else None}",
                flush=True,
            )

        self.run_async(_run())
