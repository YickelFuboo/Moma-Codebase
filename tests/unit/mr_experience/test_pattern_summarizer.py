import asyncio
import pytest
from app.repo_analysis.services.mr_experience.models import FileChange
from app.repo_analysis.services.mr_experience.pattern_summarizer import (
    PatternSummarizer,
    PatternSummarizerError,
)


class TestPatternSummarizerParse:
    def test_parse_plain_json(self):
        data = PatternSummarizer._parse_json(
            '{"extractable":true,"experiences":[{"title":"改告警","scenario":"告警策略重构","patterns":["x"],"quality_score":0.9}]}'
        )
        assert data["experiences"][0]["title"] == "改告警"
        assert data["experiences"][0]["patterns"][0] == "x"

    def test_parse_fenced_json(self):
        raw = '```json\n{"extractable":true,"experiences":[{"title":"t","scenario":"s","patterns":["p"],"quality_score":0.8}]}\n```'
        data = PatternSummarizer._parse_json(raw)
        assert data["experiences"][0]["title"] == "t"

    def test_parse_strips_redacted_thinking(self):
        raw = '<think>internal</think>{"extractable":false,"skip_reason":"x"}'
        data = PatternSummarizer._parse_json(raw)
        assert data["extractable"] is False

    def test_parse_invalid_raises(self):
        with pytest.raises(PatternSummarizerError):
            PatternSummarizer._parse_json("not-json")


class TestPatternSummarizerExtract:
    def test_prefilter_skips_lock_only(self):
        async def _run():
            return await PatternSummarizer.summarize(
                "bump lock",
                [FileChange(path="package-lock.json", status="M", additions=100, deletions=100)],
                "abc",
            )

        result = asyncio.run(_run())
        assert result.extractable is False
        assert result.skip_reason

    def test_llm_skip_not_extractable(self, monkeypatch):
        class _Fake:
            async def chat_stream(self, **kwargs):
                async def _gen():
                    yield '{"extractable":false,"skip_reason":"纯格式化"}'

                return _gen(), {}

        monkeypatch.setattr(
            "app.repo_analysis.services.mr_experience.pattern_summarizer.llm_factory.create_model",
            lambda: _Fake(),
        )

        async def _run():
            return await PatternSummarizer.summarize(
                "style only",
                [FileChange(path="a.py", status="M", additions=2, deletions=2)],
                "abc",
            )

        result = asyncio.run(_run())
        assert result.extractable is False
        assert "格式化" in result.skip_reason

    def test_llm_extractable_returns_pattern(self, monkeypatch):
        class _Fake:
            async def chat_stream(self, **kwargs):
                async def _gen():
                    yield (
                        '{"extractable":true,"experiences":['
                        '{"title":"新增 skill","scenario":"扩展 agent 能力时",'
                        '"patterns":["skill 与 tool 分离"],'
                        '"quality_score":0.82,'
                        '"plan":["定义 skill 目录","注册到 agent"],'
                        '"anchors":["app/agents/skills/"],'
                        '"relevant_files":["app/agents/skills/foo.py"]}'
                        ']}'
                    )

                return _gen(), {}

        monkeypatch.setattr(
            "app.repo_analysis.services.mr_experience.pattern_summarizer.llm_factory.create_model",
            lambda: _Fake(),
        )

        async def _run():
            return await PatternSummarizer.summarize(
                "add skill",
                [FileChange(path="app/agents/skills/foo.py", status="A", additions=50, deletions=0)],
                "deadbeef",
            )

        result = asyncio.run(_run())
        assert result.extractable is True
        assert len(result.patterns) == 1
        pattern = result.patterns[0]
        assert pattern.title == "新增 skill"
        assert pattern.scenario
        assert pattern.patterns
        assert pattern.quality_score == pytest.approx(0.82)
        assert pattern.plan
        assert pattern.anchors
        assert pattern.relevant_files == ["app/agents/skills/foo.py"]

    def test_build_patterns_fills_relevant_files_from_commit(self):
        data = {
            "extractable": True,
            "experiences": [
                {
                    "title": "鉴权校验集中化",
                    "scenario": "接入 JWT 校验时",
                    "patterns": ["统一 Token 校验入口"],
                    "quality_score": 0.8,
                }
            ],
        }
        patterns = PatternSummarizer._build_patterns(
            data,
            "sha",
            "msg",
            files=[
                FileChange(path="app/utils/auth/jwt_validator.py", status="M", additions=20, deletions=2),
                FileChange(path="README.md", status="M", additions=1, deletions=0),
            ],
        )
        assert len(patterns) == 1
        assert patterns[0].relevant_files[0].endswith("jwt_validator.py")
        assert any("auth" in a for a in patterns[0].anchors)


class TestPatternSummarizerReusability:
    def test_cap_score_drops_changelog_style(self):
        score = PatternSummarizer._cap_score_if_mr_summary(
            title="批量精简 Skill 文档",
            scenario="文档太长时",
            patterns=["一次性批量处理所有 SKILL.md", "纯删减式瘦身，零新增"],
            score=0.68,
        )
        assert score <= 0.5

    def test_build_patterns_skips_low_reusability(self):
        data = {
            "extractable": True,
            "experiences": [
                {
                    "title": "批量精简",
                    "scenario": "s",
                    "patterns": ["一次性批量", "纯删减"],
                    "quality_score": 0.68,
                },
                {
                    "title": "Skill Hub 迁移",
                    "scenario": "跨 agent 复用 skill 时",
                    "patterns": ["按 domain 分类存放 skill，而非 agent 私有目录"],
                    "quality_score": 0.78,
                },
            ],
        }
        patterns = PatternSummarizer._build_patterns(data, "sha", "msg")
        assert len(patterns) == 1
        assert patterns[0].title == "Skill Hub 迁移"
