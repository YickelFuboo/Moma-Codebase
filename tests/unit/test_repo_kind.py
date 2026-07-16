from app.repo_mgmt.models.git_repo_mgmt import RepoKind


class TestRepoKind:
    def test_values(self):
        assert RepoKind.CODE == "code"
        assert RepoKind.LIB == "lib"
        assert RepoKind.VALUES == ("code", "lib")

    def test_not_enum_style_value(self):
        assert not hasattr(RepoKind.CODE, "value") or RepoKind.CODE == "code"
