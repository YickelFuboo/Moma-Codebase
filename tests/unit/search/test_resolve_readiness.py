import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from app.repo_analysis.services.search_resolve.errors import ResolveIndexNotReady
from app.repo_analysis.services.search_resolve.readiness import ResolveReadiness


class TestResolveReadiness:
    def test_ensure_searchable_ok(self):
        async def _run():
            with patch(
                "app.repo_analysis.services.search_resolve.readiness.AnalysisService.get_summary",
                new=AsyncMock(
                    return_value={
                        "analysis_summary": {
                            "searchable": True,
                            "searchable_files": 3,
                        },
                        "scan": {"scan_status": "completed"},
                    }
                ),
            ):
                out = await ResolveReadiness.ensure_searchable("r1")
                assert out["analysis_summary"]["searchable"] is True

        asyncio.run(_run())

    def test_ensure_searchable_raises_index_not_ready(self):
        async def _run():
            with patch(
                "app.repo_analysis.services.search_resolve.readiness.AnalysisService.get_summary",
                new=AsyncMock(
                    return_value={
                        "analysis_summary": {
                            "searchable": False,
                            "searchable_files": 0,
                            "scan_active_in_process": False,
                        },
                        "scan": {"scan_status": "idle"},
                        "stale_hint": "never_scanned",
                        "status_message": "尚不可检索",
                    }
                ),
            ):
                with pytest.raises(ResolveIndexNotReady) as ei:
                    await ResolveReadiness.ensure_searchable("r1")
                exc = ei.value
                assert exc.error_code == "index_not_ready"
                assert exc.details.get("hint")
                assert "尚未完成分析" in str(exc) or "无可搜索" in str(exc)

        asyncio.run(_run())
