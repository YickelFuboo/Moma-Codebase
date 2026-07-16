import asyncio
import pytest
from app.lib_analysis.schemes.public_api import PublicApi
from app.lib_analysis.services.api_summary import ApiSummaryService


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _FakeLLM:
    def __init__(self, chunks):
        self._chunks = chunks

    async def chat_stream(self, **kwargs):
        return _FakeStream(list(self._chunks)), {}


class TestApiSummarySummarize:
    def test_summarize_uses_llm_text(self, monkeypatch):
        async def _run():
            monkeypatch.setattr(
                "app.lib_analysis.services.api_summary.api_summary.llm_factory.create_model",
                lambda: _FakeLLM(["功能：读取文件\n关键参数：path\n返回：内容"]),
            )
            api = PublicApi(
                name="read",
                kind="function",
                signature="read()",
                file_path="a.py",
                language="python",
                start_line=1,
                end_line=2,
            )
            return await ApiSummaryService.summarize(api)

        text = asyncio.run(_run())
        assert "读取文件" in text

    def test_summarize_falls_back_on_llm_error_text(self, monkeypatch):
        async def _run():
            monkeypatch.setattr(
                "app.lib_analysis.services.api_summary.api_summary.llm_factory.create_model",
                lambda: _FakeLLM(["llm error: boom"]),
            )
            api = PublicApi(
                name="read",
                kind="function",
                signature="read()",
                file_path="a.py",
                language="python",
                start_line=1,
                end_line=2,
                docstring="doc",
            )
            return await ApiSummaryService.summarize(api)

        text = asyncio.run(_run())
        assert "doc" in text

    def test_summarize_falls_back_on_exception(self, monkeypatch):
        def _boom():
            raise RuntimeError("no llm")

        async def _run():
            monkeypatch.setattr(
                "app.lib_analysis.services.api_summary.api_summary.llm_factory.create_model",
                _boom,
            )
            api = PublicApi(
                name="X",
                kind="class",
                signature="class X",
                file_path="a.py",
                language="python",
                start_line=1,
                end_line=2,
            )
            return await ApiSummaryService.summarize(api)

        text = asyncio.run(_run())
        assert "X" in text
