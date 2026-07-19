from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from app.repo_analysis.models.analysis_status import FileAnalysisStatus, RepoAnalysisStatus
from app.repo_analysis.services.analysis_service import AnalysisService


class TestAnalyzeStatusVisualization:
    def test_get_summary_adds_stale_and_incremental(self, tmp_path, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "enable_incremental_scan", True)
        monkeypatch.setattr(settings, "incremental_scan_interval_sec", 120)

        finished = datetime.now() - timedelta(hours=2)
        fail_row = SimpleNamespace(
            file_path="a.py",
            last_error="boom",
            updated_at=datetime.now(),
        )

        async def _run():
            db = MagicMock()
            repo = SimpleNamespace(local_path=str(tmp_path))
            status_rows = [
                (FileAnalysisStatus.COMPLETED.value, 3),
                (FileAnalysisStatus.EMBEDDED.value, 2),
                (FileAnalysisStatus.PENDING.value, 1),
                (FileAnalysisStatus.FAILED.value, 1),
            ]
            exec_result = MagicMock()
            exec_result.all.return_value = status_rows
            db.execute = AsyncMock(return_value=exec_result)
            db.scalar = AsyncMock(return_value=repo)
            fail_scalars = MagicMock()
            fail_scalars.all.return_value = [fail_row]
            db.scalars = AsyncMock(return_value=fail_scalars)

            class _CM:
                async def __aenter__(self):
                    return db

                async def __aexit__(self, *args):
                    return False

            with patch(
                "app.repo_analysis.services.analysis_service.get_db_session",
                return_value=_CM(),
            ), patch.object(
                AnalysisService,
                "get_scan_status",
                new=AsyncMock(
                    return_value={
                        "scan_status": RepoAnalysisStatus.COMPLETED.value,
                        "last_scan_finished_at": finished.isoformat(),
                    }
                ),
            ):
                return await AnalysisService.get_summary("repo-1")

        out = asyncio.run(_run())
        assert out["analysis_summary"]["pending_files"] == 1
        assert out["analysis_summary"]["embedded_files"] == 2
        assert out["analysis_summary"]["searchable_files"] == 5
        assert out["analysis_summary"]["searchable"] is True
        assert out["analysis_summary"]["enrichment_pending"] is True
        assert out["stale"] is True
        assert "pending_files" in (out["stale_hint"] or "")
        assert "symbol_enrichment_pending" in (out["stale_hint"] or "")
        assert out["incremental_scan"]["enabled"] is True
        assert out["incremental_scan"]["interval_sec"] == 120
        assert out["index_age_seconds"] is not None
        assert out["index_age_seconds"] >= 7000
        assert out["recent_failures"][0]["file_path"] == "a.py"
        assert "ignore" in out
