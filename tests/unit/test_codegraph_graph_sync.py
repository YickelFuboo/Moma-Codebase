import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from app.repo_analysis.services.analysis_service import AnalysisService


class TestHasExistingGraphIndex:
    def test_detects_codegraph_dir(self, tmp_path: Path):
        (tmp_path / ".codegraph").mkdir()
        assert AnalysisService.has_existing_graph_index(str(tmp_path), had_prior_scan=False) is True

    def test_prior_scan_without_dir(self, tmp_path: Path):
        assert AnalysisService.has_existing_graph_index(str(tmp_path), had_prior_scan=True) is True
        assert AnalysisService.has_existing_graph_index(str(tmp_path), had_prior_scan=False) is False


class TestRunCodeGraphMode:
    def test_full_generate_when_no_index(self, monkeypatch, tmp_path: Path):
        calls = {"generate": 0, "update": 0}

        class _Gen:
            async def generate_graph(self, clean_stale=False):
                calls["generate"] += 1

            async def update_files(self, file_paths):
                calls["update"] += 1

            def close(self):
                return None

        class _Provider:
            name = "codegraph"

        monkeypatch.setattr(
            "app.repo_analysis.services.analysis_service.CodeGraphGateway.create_generator",
            staticmethod(lambda *a, **k: _Gen()),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.analysis_service.CodeGraphGateway.get_provider",
            classmethod(lambda cls: _Provider()),
        )

        async def _run():
            await AnalysisService._run_code_graph(
                repo_id="r1",
                repo_path=str(tmp_path),
                scan_task=None,
                incremental=False,
            )

        asyncio.run(_run())
        assert calls["generate"] == 1
        assert calls["update"] == 0

    def test_incremental_update_codegraph(self, monkeypatch, tmp_path: Path):
        calls = {"generate": 0, "update": 0, "paths": None}

        class _Gen:
            async def generate_graph(self, clean_stale=False):
                calls["generate"] += 1

            async def update_files(self, file_paths):
                calls["update"] += 1
                calls["paths"] = list(file_paths or [])

            def close(self):
                return None

        class _Provider:
            name = "codegraph"

        monkeypatch.setattr(
            "app.repo_analysis.services.analysis_service.CodeGraphGateway.create_generator",
            staticmethod(lambda *a, **k: _Gen()),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.analysis_service.CodeGraphGateway.get_provider",
            classmethod(lambda cls: _Provider()),
        )

        async def _run():
            await AnalysisService._run_code_graph(
                repo_id="r1",
                repo_path=str(tmp_path),
                scan_task=None,
                incremental=True,
            )

        asyncio.run(_run())
        assert calls["generate"] == 0
        assert calls["update"] == 1
        assert calls["paths"] == []

    def test_incremental_builtin_waits_scan_and_passes_pending(self, monkeypatch, tmp_path: Path):
        calls = {"update": 0, "paths": None}
        f = tmp_path / "a.py"
        f.write_text("x=1\n", encoding="utf-8")

        class _Gen:
            async def generate_graph(self, clean_stale=False):
                return None

            async def update_files(self, file_paths):
                calls["update"] += 1
                calls["paths"] = list(file_paths or [])

            def close(self):
                return None

        class _Provider:
            name = "builtin"

        monkeypatch.setattr(
            "app.repo_analysis.services.analysis_service.CodeGraphGateway.create_generator",
            staticmethod(lambda *a, **k: _Gen()),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.analysis_service.CodeGraphGateway.get_provider",
            classmethod(lambda cls: _Provider()),
        )
        monkeypatch.setattr(
            AnalysisService,
            "_list_pending_abs_paths",
            staticmethod(AsyncMock(return_value=[str(f)])),
        )

        async def _scan():
            return None

        async def _run():
            scan_task = asyncio.create_task(_scan())
            await AnalysisService._run_code_graph(
                repo_id="r1",
                repo_path=str(tmp_path),
                scan_task=scan_task,
                incremental=True,
            )

        asyncio.run(_run())
        assert calls["update"] == 1
        assert calls["paths"] == [str(f)]
