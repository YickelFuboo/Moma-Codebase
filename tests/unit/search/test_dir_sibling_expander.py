from app.repo_analysis.services.dir_sibling_expander import DirSiblingExpander


class TestDirSiblingExpander:
    def test_adds_same_dir_siblings_not_in_primary(self):
        primary = [{"file_path": "app/utils/auth/jwt_validator.py", "score": 3.0}]
        also = [{"file_path": "app/utils/auth/other.py", "score": 1.0}]
        candidates = [
            "app/utils/auth/jwt_validator.py",
            "app/utils/auth/jwt_middleware.py",
            "app/utils/auth/other.py",
            "app/agents/core/base.py",
        ]
        out = DirSiblingExpander.expand(
            primary=primary,
            also=also,
            candidate_paths=candidates,
        )
        paths = {it["file_path"] for it in out}
        assert "app/utils/auth/jwt_middleware.py" in paths
        assert "app/utils/auth/other.py" in paths
        assert "app/agents/core/base.py" not in paths
        assert all(it["file_path"] != "app/utils/auth/jwt_validator.py" for it in out)

    def test_empty_primary_keeps_also(self):
        also = [{"file_path": "a.py", "score": 1.0}]
        out = DirSiblingExpander.expand(primary=[], also=also, candidate_paths=["a.py", "b.py"])
        assert out == also
