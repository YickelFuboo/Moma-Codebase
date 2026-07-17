from app.repo_analysis.services.mr_experience.change_filter import ChangeFilter
from app.repo_analysis.services.mr_experience.models import FileChange


class TestChangeFilterExclude:
    def test_exclude_lock_and_vendor(self):
        assert ChangeFilter.should_exclude("package-lock.json") is True
        assert ChangeFilter.should_exclude("node_modules/x/y.js") is True
        assert ChangeFilter.should_exclude("app/svc.py") is False

    def test_select_top_k_by_churn(self):
        files = [
            FileChange(path="a.py", status="M", additions=1, deletions=0),
            FileChange(path="b.py", status="M", additions=20, deletions=5),
            FileChange(path="package-lock.json", status="M", additions=100, deletions=100),
            FileChange(path="c.py", status="A", additions=3, deletions=0),
        ]
        selected = ChangeFilter.select(files, top_k=2)
        paths = [f.path for f in selected]
        assert paths[0] == "b.py"
        assert "package-lock.json" not in paths
        assert len(selected) == 2

    def test_status_action(self):
        assert ChangeFilter.status_action("A") == "新增"
        assert ChangeFilter.status_action("D") == "删除"
        assert ChangeFilter.status_action("M") == "修改"


class TestChangeFilterPrefilter:
    def test_skip_lock_only(self):
        reason = ChangeFilter.prefilter_skip_reason(
            "bump deps",
            [FileChange(path="package-lock.json", status="M", additions=100, deletions=100)],
        )
        assert reason

    def test_skip_empty_after_select(self):
        reason = ChangeFilter.prefilter_skip_reason(
            "only vendor",
            [FileChange(path="node_modules/x.js", status="M", additions=1, deletions=0)],
        )
        assert reason == "无有效变更文件"

    def test_keep_meaningful_change(self):
        reason = ChangeFilter.prefilter_skip_reason(
            "add skill module",
            [FileChange(path="app/skill.py", status="A", additions=80, deletions=0)],
        )
        assert reason is None
