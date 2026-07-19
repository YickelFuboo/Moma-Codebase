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

    def test_prepare_terms_precompiles_identifier(self):
        prepared = ContentGrepService._prepare_terms(["AuthService", "鉴权", "AuthService"])
        assert len(prepared) == 2
        ident = next(p for p in prepared if p.raw == "AuthService")
        assert ident.is_identifier
        assert ident.ident_pattern is not None
        assert ident.ident_pattern.search("class AuthService:")

    def test_early_stop_when_enough_strong_hits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ContentGrepService, "EARLY_STOP_MIN_SCANNED", 5)
        monkeypatch.setattr(ContentGrepService, "EARLY_STOP_STRONG_MIN", 3)
        for i in range(20):
            (tmp_path / f"f{i}.py").write_text(
                f"class Marker{i}:\n    x = {i}\n",
                encoding="utf-8",
            )
        # 用同一标识符造多文件强命中
        for i in range(5):
            (tmp_path / f"hit{i}.py").write_text(
                "class SharedHit:\n    pass\n",
                encoding="utf-8",
            )
        hits = ContentGrepService.search(
            str(tmp_path),
            ["SharedHit"],
            extensions={".py"},
            top_k=10,
            builtin_dir_names=set(),
        )
        assert len(hits) >= 3
        assert all(float(h["score"]) >= 2.5 for h in hits[:3])
