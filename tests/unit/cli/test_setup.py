import asyncio
from unittest.mock import AsyncMock, patch
from app.cli.setup import SetupService


class TestSetupService:
    def test_skip_analyze_already_registered(self, tmp_path):
        repo_path = tmp_path / "demo"
        repo_path.mkdir()

        class _Repo:
            id = "r1"
            kind = "code"
            local_path = str(repo_path)
            repository_name = "demo"
            description = ""
            git_provider = None
            repository_url = ""
            branch = None
            created_at = None
            updated_at = None
            user_id = "default"

        class _CM:
            async def __aenter__(self):
                db = AsyncMock()
                return db

            async def __aexit__(self, *args):
                return False

        async def _run():
            with patch(
                "app.cli.setup.DoctorService.run",
                new=AsyncMock(return_value={"ok": True, "checks": []}),
            ), patch(
                "app.cli.setup.get_db_session",
                return_value=_CM(),
            ), patch(
                "app.cli.setup.RepoResolver.get_by_path",
                new=AsyncMock(return_value=_Repo()),
            ), patch(
                "app.cli.setup.get_repo_by_path",
                new=AsyncMock(return_value=_Repo()),
            ), patch(
                "app.cli.setup.SetupService._summary_for",
                new=AsyncMock(
                    return_value={
                        "analysis_summary": {
                            "searchable": True,
                            "searchable_files": 2,
                        },
                        "status_message": "索引可检索",
                        "stale_hint": None,
                    }
                ),
            ):
                return await SetupService.run(
                    str(repo_path),
                    skip_analyze=True,
                    wait_sec=1,
                    poll_ms=100,
                )

        out = asyncio.run(_run())
        assert out["ok"] is True
        assert out["searchable"] is True
        assert out["analyze_started"] is False
        assert "search resolve" in out["next"]["command"]

    def test_doctor_failed_short_circuits(self, tmp_path):
        repo_path = tmp_path / "demo"
        repo_path.mkdir()

        async def _run():
            with patch(
                "app.cli.setup.DoctorService.run",
                new=AsyncMock(return_value={"ok": False, "checks": [{"name": "embedding", "ok": False}]}),
            ):
                return await SetupService.run(str(repo_path), skip_analyze=True)

        out = asyncio.run(_run())
        assert out["ok"] is False
        assert out["error"]["code"] == "doctor_failed"
