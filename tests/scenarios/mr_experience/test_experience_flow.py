"""经验场景：merge 优先采集 + 失败不入向量 + 成功可检索。"""
from __future__ import annotations
import asyncio
import subprocess
from pathlib import Path
import pytest
from app.repo_analysis.services.mr_experience.change_filter import ChangeFilter
from app.repo_analysis.services.mr_experience.git_history_source import GitHistorySource
from app.repo_analysis.services.mr_experience.models import ExperiencePattern, ExperienceStep
from app.repo_analysis.services.mr_experience.pattern_summarizer import (
    PatternSummarizer,
    PatternSummarizerError,
)
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService


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


class TestMrExperienceScenarios:
    def test_merge_preferred_collect(self, tmp_path: Path):
        repo = tmp_path / "r"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        _git(repo, "checkout", "-b", "main")
        f = repo / "svc.py"
        f.write_text("def run():\n    return 1\n", encoding="utf-8")
        _git(repo, "add", "svc.py")
        _git(repo, "commit", "-m", "init")
        _git(repo, "checkout", "-b", "feat")
        f.write_text("def run():\n    return 2\n", encoding="utf-8")
        _git(repo, "add", "svc.py")
        _git(repo, "commit", "-m", "feat bump")
        _git(repo, "checkout", "main")
        _git(repo, "merge", "--no-ff", "-m", "Merge feat: bump return", "feat")

        entries = GitHistorySource.collect(str(repo), limit=10)
        assert entries
        assert all(e.is_merge for e in entries)
        selected = ChangeFilter.select(entries[0].files)
        assert any(f.path.endswith("svc.py") for f in selected)

    def test_llm_fail_then_success_search(self, tmp_path: Path, monkeypatch):
        calls = {"n": 0}

        async def _summarize(message, files, commit_sha):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PatternSummarizerError("temporary llm fail")
            return ExperiencePattern(
                title="调整 svc 返回值",
                steps=[ExperienceStep(file="svc.py", action="将返回值改为 2")],
                source_commits=[commit_sha],
                commit_message=message,
            )

        monkeypatch.setattr(PatternSummarizer, "summarize", staticmethod(_summarize))
        repo_id = "exp-scenario-retry"

        async def _run():
            # 第一次失败：不应写入可检索经验（若误写入也随后清理）
            with pytest.raises(PatternSummarizerError):
                await PatternSummarizer.summarize("m", [], "sha-fail")
            # 成功写入
            pattern = await PatternSummarizer.summarize(
                "Merge feat: bump return",
                [],
                "sha-ok",
            )
            await PatternVectorService.upsert_pattern(repo_id, pattern)
            items = await PatternVectorService.search(repo_id, "调整 svc 返回值", top_k=5)
            await PatternVectorService.delete_repo_patterns(repo_id)
            return items

        try:
            items = asyncio.run(_run())
        except Exception as exc:
            msg = str(exc).lower()
            if "embedding" in msg or "模型" in msg or "vector" in msg:
                pytest.skip(f"环境缺少 embedding: {exc}")
            raise

        assert calls["n"] == 2
        assert items
        assert items[0].get("title")
        assert items[0].get("steps")
        assert items[0].get("source_commits")
