from unittest.mock import AsyncMock, patch
import asyncio
from app.cli.doctor import DoctorService
from app.config.settings import settings


class TestDoctorService:
    def test_runtime_dir_check(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "runtime_data_dir", str(tmp_path))
        row = DoctorService._check_runtime_dir()
        assert row["ok"] is True
        assert row["writable"] is True

    def test_run_aggregates_ok(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "runtime_data_dir", str(tmp_path))

        async def _run():
            with patch.object(
                DoctorService,
                "_check_database",
                new=AsyncMock(return_value={"name": "database", "ok": True}),
            ), patch.object(
                DoctorService,
                "_check_vector_store",
                return_value={"name": "vector_store", "ok": True},
            ), patch.object(
                DoctorService,
                "_check_codegraph",
                return_value={"name": "codegraph", "ok": True},
            ), patch.object(
                DoctorService,
                "_check_repos",
                new=AsyncMock(
                    return_value={"name": "registered_repos", "ok": True, "total": 0}
                ),
            ):
                return await DoctorService.run()

        out = asyncio.run(_run())
        assert out["ok"] is True
        assert len(out["checks"]) == 5
