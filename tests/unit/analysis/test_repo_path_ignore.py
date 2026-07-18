from app.repo_analysis.services.repo_path_ignore import RepoPathIgnore


class TestRepoPathIgnore:
    def test_builtin_and_dot_dirs(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        ignorer = RepoPathIgnore.load(str(root))
        assert ignorer.should_prune_dir("node_modules", "node_modules")
        assert ignorer.should_prune_dir(".hidden", ".hidden")
        assert not ignorer.should_prune_dir("app", "app")

    def test_gitignore_file_pattern(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / ".gitignore").write_text("*.log\nbuild/\n", encoding="utf-8")
        ignorer = RepoPathIgnore.load(str(root))
        assert ignorer.gitignore_loaded is True
        assert ignorer.should_ignore_file("tmp/app.log")
        assert ignorer.should_prune_dir("build", "build")
        assert not ignorer.should_ignore_file("app/main.py")

    def test_momaignore_and_negation(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / ".momaignore").write_text("vendor/\n!vendor/keep.py\n", encoding="utf-8")
        ignorer = RepoPathIgnore.load(str(root))
        assert ignorer.momaignore_loaded is True
        assert ignorer.should_prune_dir("vendor", "vendor")

    def test_filter_walk_dirs(self, tmp_path):
        root = tmp_path / "repo"
        (root / "app").mkdir(parents=True)
        (root / "node_modules").mkdir()
        ignorer = RepoPathIgnore.load(str(root))
        dirs = ["app", "node_modules", ".git"]
        excluded = ignorer.filter_walk_dirs(str(root), dirs)
        assert dirs == ["app"]
        assert "node_modules" in excluded or any("node_modules" in e for e in excluded)
