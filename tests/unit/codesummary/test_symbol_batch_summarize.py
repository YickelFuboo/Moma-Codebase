import asyncio
import json
from unittest.mock import patch
from app.repo_analysis.services.codesummary.batch_summarizer import (
    SymbolBatchSummarizer,
    SymbolSummaryRequest,
)
from app.repo_analysis.services.codesummary.model import ContentType


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _CountingLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.last_kwargs = None

    async def chat_stream(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        text = self.responses.pop(0) if self.responses else "[]"
        return _FakeStream([text]), None


class TestSymbolBatchParse:
    def test_parse_valid_array(self):
        raw = json.dumps(
            [
                {"id": 0, "summary": "鉴权校验 JWT"},
                {"id": 1, "summary": "会话存储"},
            ],
            ensure_ascii=False,
        )
        parsed = SymbolBatchSummarizer.parse_batch_response(raw, expected=2)
        assert parsed == {0: "鉴权校验 JWT", 1: "会话存储"}

    def test_parse_markdown_fenced(self):
        raw = """```json
[{"id": 0, "summary": "a"}, {"id": 1, "summary": "b"}]
```"""
        parsed = SymbolBatchSummarizer.parse_batch_response(raw, expected=2)
        assert parsed[0] == "a"
        assert parsed[1] == "b"

    def test_parse_invalid_returns_none(self):
        assert SymbolBatchSummarizer.parse_batch_response("not json", expected=2) is None
        assert SymbolBatchSummarizer.parse_batch_response("[]", expected=2) is None

    def test_build_batch_user_question_truncates(self):
        long_src = "x" * 5000
        q = SymbolBatchSummarizer.build_batch_user_question(
            [SymbolSummaryRequest(source=long_src, content_type=ContentType.FUNCTION, name="foo")],
            max_chars_per_symbol=100,
        )
        assert "id=0" in q
        assert "foo" in q
        assert "[truncated]" in q
        assert len(q) < 5000


class TestSymbolBatchSummarize:
    def test_batch_size_one_uses_single_path(self):
        llm = _CountingLLM(["单条摘要 检索词：auth"])

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.code_summary.llm_factory.create_model",
                return_value=llm,
            ):
                return await SymbolBatchSummarizer.summarize_many(
                    [
                        SymbolSummaryRequest(
                            source="def a():\n    return 1\n",
                            content_type=ContentType.FUNCTION,
                            name="a",
                        )
                    ],
                    batch_size=1,
                    concurrency=1,
                )

        out = asyncio.run(_run())
        assert len(out) == 1
        assert "单条摘要" in out[0]
        assert llm.calls == 1

    def test_batch_success_one_call_for_three(self):
        payload = json.dumps(
            [
                {"id": 0, "summary": "摘要0 检索词：a"},
                {"id": 1, "summary": "摘要1 检索词：b"},
                {"id": 2, "summary": "摘要2 检索词：c"},
            ],
            ensure_ascii=False,
        )
        llm = _CountingLLM([payload])

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.batch_summarizer.llm_factory.create_model",
                return_value=llm,
            ):
                return await SymbolBatchSummarizer.summarize_many(
                    [
                        SymbolSummaryRequest("def a():\n  return 1\n", ContentType.FUNCTION, "a"),
                        SymbolSummaryRequest("def b():\n  return 2\n", ContentType.FUNCTION, "b"),
                        SymbolSummaryRequest("class C:\n  pass\n", ContentType.CLASS, "C"),
                    ],
                    batch_size=6,
                    concurrency=1,
                )

        out = asyncio.run(_run())
        assert out == ["摘要0 检索词：a", "摘要1 检索词：b", "摘要2 检索词：c"]
        assert llm.calls == 1

    def test_batch_bad_json_falls_back_to_singles(self):
        llm = _CountingLLM(
            [
                "这不是JSON",
                "回退A 检索词：a",
                "回退B 检索词：b",
            ]
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.batch_summarizer.llm_factory.create_model",
                return_value=llm,
            ), patch(
                "app.repo_analysis.services.codesummary.code_summary.llm_factory.create_model",
                return_value=llm,
            ):
                return await SymbolBatchSummarizer.summarize_many(
                    [
                        SymbolSummaryRequest("def a():\n  return 1\n", ContentType.FUNCTION, "a"),
                        SymbolSummaryRequest("def b():\n  return 2\n", ContentType.FUNCTION, "b"),
                    ],
                    batch_size=6,
                    concurrency=1,
                )

        out = asyncio.run(_run())
        assert len(out) == 2
        assert "回退A" in out[0]
        assert "回退B" in out[1]
        assert llm.calls == 3

    def test_partial_missing_id_refills(self):
        payload = json.dumps([{"id": 0, "summary": "仅有0"}], ensure_ascii=False)
        llm = _CountingLLM([payload, "补齐1 检索词：b"])

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.batch_summarizer.llm_factory.create_model",
                return_value=llm,
            ), patch(
                "app.repo_analysis.services.codesummary.code_summary.llm_factory.create_model",
                return_value=llm,
            ):
                return await SymbolBatchSummarizer.summarize_many(
                    [
                        SymbolSummaryRequest("def a():\n  return 1\n", ContentType.FUNCTION, "a"),
                        SymbolSummaryRequest("def b():\n  return 2\n", ContentType.FUNCTION, "b"),
                    ],
                    batch_size=6,
                    concurrency=1,
                )

        out = asyncio.run(_run())
        assert out[0] == "仅有0"
        assert "补齐1" in out[1]
        assert llm.calls == 2

    def test_context_overflow_splits_then_succeeds(self):
        half0 = json.dumps(
            [{"id": 0, "summary": "H0"}, {"id": 1, "summary": "H1"}],
            ensure_ascii=False,
        )
        half1 = json.dumps(
            [{"id": 0, "summary": "H2"}, {"id": 1, "summary": "H3"}],
            ensure_ascii=False,
        )
        llm = _CountingLLM(
            [
                "llm error: context_overflow",
                half0,
                half1,
            ]
        )

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.batch_summarizer.llm_factory.create_model",
                return_value=llm,
            ):
                return await SymbolBatchSummarizer.summarize_many(
                    [
                        SymbolSummaryRequest("def a():\n  return 1\n", ContentType.FUNCTION, "a"),
                        SymbolSummaryRequest("def b():\n  return 2\n", ContentType.FUNCTION, "b"),
                        SymbolSummaryRequest("def c():\n  return 3\n", ContentType.FUNCTION, "c"),
                        SymbolSummaryRequest("def d():\n  return 4\n", ContentType.FUNCTION, "d"),
                    ],
                    batch_size=6,
                    concurrency=1,
                )

        out = asyncio.run(_run())
        assert out == ["H0", "H1", "H2", "H3"]
        assert llm.calls == 3
