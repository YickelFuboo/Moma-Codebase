from app.repo_analysis.services.search_snippet import SearchSnippetAttacher


class TestSearchSnippetAttacher:
    def test_attach_range(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        f = root / "a.py"
        f.write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")
        payload = {
            "path": str(root),
            "query": "q",
            "total": 1,
            "items": [
                {
                    "file_path": "a.py",
                    "start_line": 2,
                    "end_line": 4,
                }
            ],
        }
        out = SearchSnippetAttacher.attach_to_payload(payload, enabled=True)
        assert out["with_content"] is True
        assert out["items"][0]["snippet"] == "l2\nl3\nl4"

    def test_fallback_head_when_no_lines(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        f = root / "b.py"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        item = {"file_path": "b.py", "path": str(root)}
        SearchSnippetAttacher.attach_item(item, repo_root=str(root), max_lines=10)
        assert "a" in item["snippet"]

    def test_disabled(self, tmp_path):
        out = SearchSnippetAttacher.attach_to_payload(
            {"path": str(tmp_path), "items": [{"file_path": "x.py"}]},
            enabled=False,
        )
        assert out["with_content"] is False
        assert "snippet" not in out["items"][0]

    def test_blocks_path_escape(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        item = {"file_path": "../secret.txt"}
        SearchSnippetAttacher.attach_item(item, repo_root=str(root))
        assert "snippet" not in item
