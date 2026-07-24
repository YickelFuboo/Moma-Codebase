import pytest
from app.cli.schemes import ErrorCode, ExitCode, ResponseScheme


class TestResponseScheme:
    def test_success_wraps_ok_true(self):
        body = ResponseScheme.success(
            {
                "query": "JWT",
                "total": 1,
                "items": [{"file_path": "app/auth.py"}],
                "intent": "related",
            }
        )
        assert body["ok"] is True
        assert body["query"] == "JWT"
        assert ResponseScheme.validate_resolve_success(body) == []

    def test_search_profile_does_not_require_query(self):
        body = ResponseScheme.success({"total": 0, "items": []})
        assert ResponseScheme.validate_search_success(body) == []
        assert any("query" in p for p in ResponseScheme.validate_resolve_success(body))

    def test_failure_shape(self):
        body = ResponseScheme.failure(ErrorCode.REPO_NOT_FOUND, "仓库未登记: /x")
        assert body == {
            "ok": False,
            "error": {
                "code": ErrorCode.REPO_NOT_FOUND,
                "message": "仓库未登记: /x",
            },
        }
        assert ResponseScheme.validate_failure(body) == []

    def test_success_rejects_missing_items(self):
        problems = ResponseScheme.validate_search_success(
            {"ok": True, "query": "q", "total": 0}
        )
        assert any("items" in p for p in problems)

    def test_resolve_rejects_empty_item_identity(self):
        problems = ResponseScheme.validate_resolve_success(
            {
                "ok": True,
                "query": "q",
                "total": 1,
                "items": [{"score": 0.9}],
            }
        )
        assert any("file_path" in p for p in problems)

    def test_classify_repo_not_found(self):
        assert (
            ResponseScheme.classify_click_message("仓库未登记: /tmp/x")
            == ErrorCode.REPO_NOT_FOUND
        )
        assert (
            ResponseScheme.classify_click_message(
                "未找到匹配的已登记仓库（支持精确 path 或上级目录前缀）: /a"
            )
            == ErrorCode.REPO_NOT_FOUND
        )

    def test_classify_index_not_ready(self):
        assert (
            ResponseScheme.classify_click_message("索引未就绪：无可搜索文件")
            == ErrorCode.INDEX_NOT_READY
        )
        assert (
            ResponseScheme.classify_click_message("索引仍在构建中，尚无可搜索文件")
            == ErrorCode.INDEX_NOT_READY
        )

    def test_exit_codes_stable(self):
        assert ExitCode.OK == 0
        assert ExitCode.BUSINESS == 2
        assert ExitCode.TIMEOUT == 3

    def test_run_with_timeout_raises(self):
        import asyncio

        async def _slow():
            await asyncio.sleep(0.2)
            return "ok"

        async def _run():
            with pytest.raises(TimeoutError, match="超时"):
                await ResponseScheme.run_with_timeout(_slow(), 50)
            assert await ResponseScheme.run_with_timeout(_slow(), 0) == "ok"

        asyncio.run(_run())
