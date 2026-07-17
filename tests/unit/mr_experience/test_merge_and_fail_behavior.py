import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from app.repo_analysis.services.mr_experience.git_history_source import GitHistorySource
from app.repo_analysis.services.mr_experience.models import ExperiencePattern, ExperienceStep, FileChange
from app.repo_analysis.services.mr_experience.pattern_summarizer import (
    PatternSummarizer,
    PatternSummarizerError,
)
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService


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


class TestGitHistoryMergePreferred:
    def test_prefer_merge_commits_when_present(self, tmp_path: Path):
        repo = tmp_path / "r"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        # ensure main branch name
        _git(repo, "checkout", "-b", "main")
        f = repo / "a.py"
        f.write_text("x=1\n", encoding="utf-8")
        _git(repo, "add", "a.py")
        _git(repo, "commit", "-m", "base")
        _git(repo, "checkout", "-b", "feature")
        f.write_text("x=2\n", encoding="utf-8")
        _git(repo, "add", "a.py")
        _git(repo, "commit", "-m", "feature change")
        _git(repo, "checkout", "main")
        _git(repo, "merge", "--no-ff", "-m", "Merge branch feature for alert", "feature")

        entries = GitHistorySource.collect(str(repo), limit=20)
        assert entries
        assert all(e.is_merge for e in entries)
        assert any("Merge" in (e.message or "") or "alert" in (e.message or "").lower() for e in entries)


class TestPatternSummarizerNoFallback:
    def test_llm_error_raises(self, monkeypatch):
        class _Fake:
            async def chat_stream(self, **kwargs):
                async def _gen():
                    yield "llm error: boom"
                    if False:
                        yield ""

                return _gen(), {}

        monkeypatch.setattr(
            "app.repo_analysis.services.mr_experience.pattern_summarizer.llm_factory.create_model",
            lambda: _Fake(),
        )

        async def _run():
            with pytest.raises(PatternSummarizerError):
                await PatternSummarizer.summarize(
                    "msg",
                    [FileChange(path="a.py", status="M", additions=1, deletions=0)],
                    "abc",
                )

        asyncio.run(_run())


class TestPatternVectorEmbedText:
    def test_build_embed_text(self):
        pattern = ExperiencePattern(
            title="改告警",
            steps=[ExperienceStep(file="a.go", action="改触发逻辑")],
            source_commits=["abc"],
            commit_message="fix alert",
        )
        text = PatternVectorService.build_embed_text(pattern)
        assert "改告警" in text
        assert "a.go" in text
        assert "fix alert" in text


class TestFailedDoesNotUpsertVector:
    def test_summarize_fail_skips_vector(self, monkeypatch):
        upsert = AsyncMock()
        monkeypatch.setattr(PatternVectorService, "upsert_pattern", upsert)

        class _Fake:
            async def chat_stream(self, **kwargs):
                async def _gen():
                    yield "llm error: x"

                return _gen(), {}

        monkeypatch.setattr(
            "app.repo_analysis.services.mr_experience.pattern_summarizer.llm_factory.create_model",
            lambda: _Fake(),
        )

        async def _run():
            with pytest.raises(PatternSummarizerError):
                await PatternSummarizer.summarize(
                    "m",
                    [FileChange(path="a.py", status="M", additions=2, deletions=1)],
                    "sha1",
                )
            upsert.assert_not_awaited()

        asyncio.run(_run())
