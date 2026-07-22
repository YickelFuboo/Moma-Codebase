"""快速功能测试：批量摘要贯通 vectorize_and_store_symbol_summaries 入库路径。"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.repo_analysis.services.codeast.model import FileInfo
from app.repo_analysis.services.codevector.code_vector import CodeVectorService


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _BatchLLM:
    def __init__(self):
        self.calls = 0

    async def chat_stream(self, **kwargs):
        self.calls += 1
        question = str(kwargs.get("user_question") or "")
        ids = []
        for line in question.splitlines():
            if line.startswith("### id="):
                ids.append(int(line.split("id=", 1)[1].split()[0]))
        payload = [
            {"id": i, "summary": f"功能摘要{i} 检索词：sym{i}"}
            for i in ids
        ]
        return _FakeStream([json.dumps(payload, ensure_ascii=False)]), None


class TestSymbolBatchSummarizeFunctional:
    def test_vectorize_symbol_summaries_uses_batch_llm(self, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "code_analysis_symbol_summary_llm_batch_size", 6)
        monkeypatch.setattr(settings, "code_analysis_symbol_summary_llm_concurrency", 1)

        llm = _BatchLLM()
        file_info = FileInfo(
            name="demo.py",
            file_path="demo.py",
            language="python",
            functions=[
                SimpleNamespace(
                    name="alpha",
                    source_code="def alpha(x):\n    return x\n",
                    start_line=1,
                    end_line=2,
                ),
                SimpleNamespace(
                    name="beta",
                    source_code="def beta(y):\n    return y\n",
                    start_line=4,
                    end_line=5,
                ),
                SimpleNamespace(
                    name="gamma",
                    source_code="def gamma(z):\n    return z\n",
                    start_line=7,
                    end_line=8,
                ),
            ],
            classes=[],
            imports=[],
        )

        insert_mock = AsyncMock(return_value=[])
        delete_mock = AsyncMock(return_value=0)
        create_mock = AsyncMock(return_value=True)
        exists_side = AsyncMock(return_value=True)

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.batch_summarizer.llm_factory.create_model",
                return_value=llm,
            ), patch.object(
                CodeVectorService,
                "_embed_texts_best_effort",
                new=AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]),
            ), patch(
                "app.repo_analysis.services.codevector.code_vector.VECTOR_STORE_CONN.create_space",
                create_mock,
            ), patch(
                "app.repo_analysis.services.codevector.code_vector.VECTOR_STORE_CONN.delete_records",
                delete_mock,
            ), patch(
                "app.repo_analysis.services.codevector.code_vector.VECTOR_STORE_CONN.insert_records",
                insert_mock,
            ), patch(
                "app.repo_analysis.services.codevector.code_vector.VECTOR_STORE_CONN.space_exists",
                exists_side,
            ):
                await CodeVectorService.vectorize_and_store_symbol_summaries(
                    "repo-batch",
                    "demo.py",
                    file_info,
                )

        asyncio.run(_run())
        assert llm.calls == 1
        assert insert_mock.await_count == 1
        records = insert_mock.await_args.args[1]
        assert len(records) == 3
        assert records[0]["symbol_name"] == "alpha"
        assert "功能摘要0" in records[0]["summary"]
        assert records[2]["symbol_name"] == "gamma"
