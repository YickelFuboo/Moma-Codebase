import asyncio
from app.config.settings import settings
from app.repo_analysis.services.codechunk.code_chunk import LineTextChunk
from app.repo_analysis.services.codevector.code_vector import CodeVectorService
import app.repo_analysis.services.codevector.code_vector as mod


class TestEmbedMaxCharsSkip:
    def test_settings_default_12000(self):
        assert int(settings.code_analysis_embed_max_chars) == 12000

    def test_line_chunks_skip_oversize(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_embed_max_chars", 100)
        calls = {"n": 0}

        async def _fake_best_effort(texts):
            calls["n"] += 1
            return [[0.1, 0.2] for _ in texts]

        monkeypatch.setattr(CodeVectorService, "_embed_texts_best_effort", staticmethod(_fake_best_effort))

        stored = {"records": None}

        async def _fake_create_space(*_a, **_k):
            return None

        async def _fake_delete(*_a, **_k):
            return 0

        async def _fake_insert(_space, records):
            stored["records"] = records
            return []

        monkeypatch.setattr(mod.VECTOR_STORE_CONN, "create_space", _fake_create_space)
        monkeypatch.setattr(mod.VECTOR_STORE_CONN, "delete_records", _fake_delete)
        monkeypatch.setattr(mod.VECTOR_STORE_CONN, "insert_records", _fake_insert)

        chunks = [
            LineTextChunk(1, 2, "short ok text " * 2),
            LineTextChunk(3, 4, "x" * 200),
        ]
        asyncio.run(CodeVectorService.vectorize_and_store_line_chunks("r1", "a.ts", chunks))
        assert calls["n"] == 1
        assert stored["records"] is not None
        assert len(stored["records"]) == 1
        assert stored["records"][0]["start_line"] == 1
