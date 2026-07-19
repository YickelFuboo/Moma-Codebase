from app.repo_analysis.services.content_grep import ContentGrepService


class TestContentGrepService:
    def test_identifier_hit_scores_higher(self, tmp_path):
        (tmp_path / "auth.py").write_text(
            "class AuthService:\n    def login(self):\n        return True\n",
            encoding="utf-8",
        )
        (tmp_path / "other.py").write_text(
            "def helper():\n    return 'auth-token'\n",
            encoding="utf-8",
        )
        hits = ContentGrepService.search(
            str(tmp_path),
            ["AuthService"],
            extensions={".py"},
            top_k=5,
            builtin_dir_names=set(),
        )
        assert hits
        assert hits[0]["file_path"] == "auth.py"
        assert hits[0]["match_source"] == "grep"
        assert float(hits[0]["score"]) >= 2.5

    def test_respects_ignore_and_extension(self, tmp_path):
        nested = tmp_path / "pkg"
        nested.mkdir()
        (nested / "keep.py").write_text("token = 'secret'\n", encoding="utf-8")
        (nested / "skip.txt").write_text("token = 'secret'\n", encoding="utf-8")
        ignored = tmp_path / "node_modules"
        ignored.mkdir()
        (ignored / "x.py").write_text("token = 'secret'\n", encoding="utf-8")
        hits = ContentGrepService.search(
            str(tmp_path),
            ["token"],
            extensions={".py"},
            top_k=10,
        )
        paths = {h["file_path"] for h in hits}
        assert "pkg/keep.py" in paths or "pkg\\keep.py" in paths
        assert not any("node_modules" in p for p in paths)
        assert not any(p.endswith(".txt") for p in paths)
