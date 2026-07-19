import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.repo_analysis.models.analysis_status import FileAnalysisStatus
from app.repo_analysis.services.file_analysis_service import FileAnalysisService


class TestFileAnalysisPhases:
    def test_claimable_includes_embedded(self):
        assert FileAnalysisStatus.EMBEDDED.value in FileAnalysisService._claimable_statuses()

    def test_embed_phase_returns_embedded_when_symbol_on(self, tmp_path, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "code_analysis_line_chunk_enabled", True)
        monkeypatch.setattr(settings, "code_analysis_symbol_summary_enabled", True)
        src = tmp_path / "a.py"
        src.write_text("def foo():\n    return 1\n", encoding="utf-8")

        async def _run():
            with patch(
                "app.repo_analysis.services.file_analysis_service.FileAstAnalyzer"
            ) as analyzer_cls, patch(
                "app.repo_analysis.services.file_analysis_service.CodeChunkService"
            ) as chunk_cls, patch(
                "app.repo_analysis.services.file_analysis_service.CodeVectorService"
            ) as vector_cls:
                analyzer_cls.return_value.analyze_file = AsyncMock(return_value=SimpleNamespace())
                chunk_cls.slice_file.return_value = []
                chunk_cls.slice_symbol_bodies.return_value = []
                chunk_cls.merge_chunks.return_value = []
                vector_cls.vectorize_and_store_line_chunks = AsyncMock()
                vector_cls.vectorize_and_store_symbol_summaries = AsyncMock()
                return await FileAnalysisService._analyze_embed_phase(
                    "repo-1",
                    str(tmp_path),
                    "a.py",
                    str(src),
                )

        ok, err, next_status = asyncio.run(_run())
        assert ok is True
        assert err is None
        assert next_status == FileAnalysisStatus.EMBEDDED.value

    def test_embed_phase_returns_completed_when_symbol_off(self, tmp_path, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "code_analysis_line_chunk_enabled", True)
        monkeypatch.setattr(settings, "code_analysis_symbol_summary_enabled", False)
        src = tmp_path / "a.py"
        src.write_text("x = 1\n", encoding="utf-8")

        async def _run():
            with patch(
                "app.repo_analysis.services.file_analysis_service.FileAstAnalyzer"
            ) as analyzer_cls, patch(
                "app.repo_analysis.services.file_analysis_service.CodeChunkService"
            ) as chunk_cls, patch(
                "app.repo_analysis.services.file_analysis_service.CodeVectorService"
            ) as vector_cls:
                analyzer_cls.return_value.analyze_file = AsyncMock(return_value=None)
                chunk_cls.slice_file.return_value = []
                vector_cls.vectorize_and_store_line_chunks = AsyncMock()
                return await FileAnalysisService._analyze_embed_phase(
                    "repo-1",
                    str(tmp_path),
                    "a.py",
                    str(src),
                )

        ok, err, next_status = asyncio.run(_run())
        assert ok is True
        assert err is None
        assert next_status == FileAnalysisStatus.COMPLETED.value

    def test_symbol_phase_does_not_touch_line_chunks(self, tmp_path, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "code_analysis_symbol_summary_enabled", True)
        src = tmp_path / "a.py"
        src.write_text("def foo():\n    return 1\n", encoding="utf-8")

        async def _run():
            with patch(
                "app.repo_analysis.services.file_analysis_service.FileAstAnalyzer"
            ) as analyzer_cls, patch(
                "app.repo_analysis.services.file_analysis_service.CodeVectorService"
            ) as vector_cls:
                analyzer_cls.return_value.analyze_file = AsyncMock(
                    return_value=SimpleNamespace(functions=[], classes=[], language="python")
                )
                vector_cls.vectorize_and_store_symbol_summaries = AsyncMock()
                vector_cls.vectorize_and_store_line_chunks = AsyncMock()
                ok, err = await FileAnalysisService._analyze_symbol_phase(
                    "repo-1",
                    str(tmp_path),
                    "a.py",
                    str(src),
                )
                return ok, err, vector_cls

        ok, err, vector_cls = asyncio.run(_run())
        assert ok is True
        assert err is None
        vector_cls.vectorize_and_store_symbol_summaries.assert_awaited()
        vector_cls.vectorize_and_store_line_chunks.assert_not_called()
