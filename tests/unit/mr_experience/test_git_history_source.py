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


def _git_out(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return (completed.stdout or "").strip()


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

    def test_has_new_entries_without_prior_sha(self, tmp_path: Path):
        repo = tmp_path / "r"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        f = repo / "hello.py"
        f.write_text("x=1\n", encoding="utf-8")
        _git(repo, "add", "hello.py")
        _git(repo, "commit", "-m", "init")

        assert GitHistorySource.has_new_entries(str(repo), after_sha=None) is True

    def test_has_new_entries_detects_commits_after_last_analyzed(self, tmp_path: Path):
        repo = tmp_path / "r"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        f = repo / "hello.py"
        f.write_text("x=1\n", encoding="utf-8")
        _git(repo, "add", "hello.py")
        _git(repo, "commit", "-m", "first")
        first_sha = _git_out(repo, "rev-parse", "HEAD")
        f.write_text("x=2\n", encoding="utf-8")
        _git(repo, "add", "hello.py")
        _git(repo, "commit", "-m", "second")

        assert GitHistorySource.has_new_entries(str(repo), after_sha=first_sha) is True
        latest_sha = _git_out(repo, "rev-parse", "HEAD")
        assert GitHistorySource.has_new_entries(str(repo), after_sha=latest_sha) is False

    def test_has_new_entries_prefers_merge_commits(self, tmp_path: Path):
        repo = tmp_path / "merge_r"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")
        _git(repo, "checkout", "-b", "main")
        f = repo / "svc.py"
        f.write_text("x=1\n", encoding="utf-8")
        _git(repo, "add", "svc.py")
        _git(repo, "commit", "-m", "init")
        _git(repo, "checkout", "-b", "feat")
        f.write_text("x=2\n", encoding="utf-8")
        _git(repo, "add", "svc.py")
        _git(repo, "commit", "-m", "feat")
        _git(repo, "checkout", "main")
        _git(repo, "merge", "--no-ff", "-m", "Merge feat", "feat")
        merge_sha = _git_out(repo, "rev-parse", "HEAD")

        assert GitHistorySource.has_new_entries(str(repo), after_sha=None) is True
        assert GitHistorySource.has_new_entries(str(repo), after_sha=merge_sha) is False
