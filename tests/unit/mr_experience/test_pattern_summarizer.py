import pytest
from app.repo_analysis.services.mr_experience.pattern_summarizer import (
    PatternSummarizer,
    PatternSummarizerError,
)


class TestPatternSummarizerParse:
    def test_parse_plain_json(self):
        data = PatternSummarizer._parse_json(
            '{"title":"改告警","steps":[{"file":"a.go","action":"改触发"}]}'
        )
        assert data["title"] == "改告警"
        assert data["steps"][0]["file"] == "a.go"

    def test_parse_fenced_json(self):
        raw = '```json\n{"title":"t","steps":[{"file":"f.py","action":"x"}]}\n```'
        data = PatternSummarizer._parse_json(raw)
        assert data["title"] == "t"

    def test_parse_invalid_raises(self):
        with pytest.raises(PatternSummarizerError):
            PatternSummarizer._parse_json("not-json")
