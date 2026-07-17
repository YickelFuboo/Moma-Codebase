import subprocess
from pathlib import Path
from app.repo_analysis.services.mr_experience.git_history_source import GitHistorySource


def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


class TestGitHistorySource:
    def test_collect_ordinary_commits_when_no_merge(self, tmp_path: Path):
        repo = tmp_path / "r"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        f = repo / "hello.py"
        f.write_text("def hi():\n    return 1\n", encoding="utf-8")
        _git(repo, "add", "hello.py")
        _git(repo, "commit", "-m", "add hello helper")
        f.write_text("def hi():\n    return 2\n", encoding="utf-8")
        _git(repo, "add", "hello.py")
        _git(repo, "commit", "-m", "update hello return")

        entries = GitHistorySource.collect(str(repo), limit=10)
        assert len(entries) >= 1
        assert any("hello" in (e.message or "").lower() for e in entries)
        assert any(e.files for e in entries)
        assert all(e.is_merge is False for e in entries)
