"""标题集合准确率 UT。"""
from __future__ import annotations
from tests.scenarios.framework.accuracy import AccuracyMetrics, title_matches


class TestTitleAccuracy:
    def setup_method(self) -> None:
        AccuracyMetrics.reset()

    def test_title_matches_substring(self) -> None:
        assert title_matches(
            "Hub 模式统一管理 skill 注册、发现与加载",
            "Hub 模式统一管理 skill",
        )
        assert not title_matches("无关标题", "Hub 模式统一管理 skill")

    def test_evaluate_titles_precision_recall(self) -> None:
        score = AccuracyMetrics.evaluate_titles(
            "t1",
            [
                "Hub 模式统一管理 skill 注册、发现与加载",
                "无关模式 A",
                "Skill 从 Agent 私有目录迁移至领域分类公共目录",
            ],
            [
                "Hub 模式统一管理 skill",
                "Skill 从 Agent 私有目录迁移",
            ],
        )
        assert score.matched_count == 2
        assert score.recall == 1.0
        assert abs(score.precision - 2 / 3) < 1e-9
        assert score.extra == ["无关模式 A"]

    def test_assert_pass_titles(self) -> None:
        score = AccuracyMetrics.evaluate_titles(
            "t2",
            ["Agent 流式输出全链路贯通：从 Core yield 到前端渐进式渲染"],
            ["流式输出全链路贯通"],
        )
        AccuracyMetrics.assert_pass(score, min_precision=1.0, min_recall=1.0)
