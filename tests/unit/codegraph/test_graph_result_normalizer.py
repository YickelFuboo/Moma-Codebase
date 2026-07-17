"""图谱结果清洗与边界提示 UT。"""
from app.repo_analysis.services.codegraph.graph_result_normalizer import GraphResultNormalizer


class TestGraphResultNormalizer:
    def test_filters_noise_and_unsupported(self):
        cleaned = GraphResultNormalizer.clean_paths(
            [
                "app/cli/search.py",
                "node_modules/lodash/index.js",
                "app/foo.md",
                "app/cli/search.py",
            ],
            exclude="app/cli/main.py",
        )
        assert cleaned == ["app/cli/search.py"]

    def test_unsupported_message_for_unknown_ext(self):
        msg = GraphResultNormalizer.unsupported_file_message("docs/guide.md")
        assert msg
        assert "扩展名" in msg

    def test_unsupported_message_for_noise_path(self):
        msg = GraphResultNormalizer.unsupported_file_message("node_modules/x/index.js")
        assert msg
        assert "忽略目录" in msg

    def test_missing_symbol_message(self):
        callers = GraphResultNormalizer.missing_symbol_message("Foo", "callers")
        callees = GraphResultNormalizer.missing_symbol_message("Foo", "callees")
        assert "callers" in callers and "Foo" in callers
        assert "callees" in callees and "related" in callees

    def test_is_symbol_not_found_error(self):
        assert GraphResultNormalizer.is_symbol_not_found_error(
            'Symbol "TotallyFake" not found'
        )
        assert GraphResultNormalizer.is_symbol_not_found_error(
            'codegraph JSON 解析失败: ... Symbol "X" not found'
        )
        assert not GraphResultNormalizer.is_symbol_not_found_error("connection refused")

    def test_clean_symbol_hits(self):
        hits = GraphResultNormalizer.clean_symbol_hits(
            [
                {"name": "A", "file_path": "app/a.py", "start_line": 1},
                {"name": "", "file_path": "app/b.py"},
                {"name": "C", "file_path": "node_modules/x.js"},
                {"name": "A", "file_path": "app/a.py", "start_line": 1},
            ],
            limit=10,
        )
        assert len(hits) == 1
        assert hits[0]["name"] == "A"
