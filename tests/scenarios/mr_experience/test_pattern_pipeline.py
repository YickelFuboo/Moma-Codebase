"""经验管线场景：规则筛选 + mock LLM → 向量 → search pattern。"""
from __future__ import annotations
import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from app.repo_analysis.services.mr_experience.models import (
    ExperienceExtractionResult,
    ExperiencePattern,
    ExperienceStep,
    FileChange,
)
from app.repo_analysis.services.mr_experience.pattern_summarizer import PatternSummarizer
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService
from app.repo_analysis.services.mr_experience.change_filter import ChangeFilter


pytestmark = pytest.mark.scenario


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


class TestExperiencePatternPipeline:
    def test_filter_and_mock_summarize_then_search(self, tmp_path: Path, monkeypatch):
        async def _fake_summarize(message, files, commit_sha):
            return ExperienceExtractionResult(
                extractable=True,
                patterns=[
                    ExperiencePattern(
                        title="更新 hello 返回值",
                        scenario="修改简单函数返回值时",
                        plan=["定位 hello.py 中的 hi 函数", "调整 return 并保持调用方兼容"],
                        patterns=["单文件函数改动优先直接改定义处"],
                        anchors=["hello.py"],
                        source_commits=[commit_sha],
                        commit_message=message,
                        quality_score=0.88,
                        relevant_files=["hello.py"],
                        steps=[ExperienceStep(file="hello.py", action="将返回值从 1 改为 2")],
                    )
                ],
            )

        monkeypatch.setattr(PatternSummarizer, "summarize", staticmethod(_fake_summarize))

        repo = tmp_path / "demo"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        f = repo / "hello.py"
        f.write_text("def hi():\n    return 1\n", encoding="utf-8")
        _git(repo, "add", "hello.py")
        _git(repo, "commit", "-m", "add hello")
        f.write_text("def hi():\n    return 2\n", encoding="utf-8")
        _git(repo, "add", "hello.py")
        _git(repo, "commit", "-m", "update hello return value for callers")

        files = [
            FileChange(path="hello.py", status="M", additions=1, deletions=1),
            FileChange(path="package-lock.json", status="M", additions=90, deletions=90),
        ]
        selected = ChangeFilter.select(files, top_k=5)
        assert [x.path for x in selected] == ["hello.py"]

        async def _run():
            result = await PatternSummarizer.summarize(
                "update hello return value for callers",
                selected,
                "deadbeef",
            )
            assert result.extractable and result.patterns
            pattern = result.patterns[0]
            repo_id = "exp-scenario-demo"
            upsert = AsyncMock()
            search = AsyncMock(
                return_value=[
                    {
                        "title": pattern.title,
                        "scenario": pattern.scenario,
                        "plan": pattern.plan,
                        "patterns": pattern.patterns,
                        "anchors": pattern.anchors,
                        "relevant_files": pattern.relevant_files,
                        "source_commits": pattern.source_commits,
                    }
                ]
            )
            monkeypatch.setattr(PatternVectorService, "upsert_patterns", upsert)
            monkeypatch.setattr(PatternVectorService, "search", search)
            await PatternVectorService.upsert_patterns(repo_id, [pattern])
            items = await PatternVectorService.search(repo_id, "更新 hello 返回值", top_k=5)
            upsert.assert_awaited_once()
            search.assert_awaited_once()
            return items

        items = asyncio.run(_run())
        assert items
        assert any("hello" in str(it.get("title") or "").lower() for it in items)
