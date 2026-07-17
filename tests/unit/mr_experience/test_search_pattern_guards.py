import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.repo_mgmt.models.git_repo_mgmt import RepoKind
from app.repo_analysis.services.search_service import SearchService


class _Repo:
    def __init__(self, kind: str):
        self.kind = kind
        self.id = "r1"


class TestSearchPatternsGuards:
    def test_empty_query(self):
        async def _run():
            with pytest.raises(ValueError, match="query"):
                await SearchService.search_patterns("r1", " ")

        asyncio.run(_run())

    def test_rejects_lib_kind(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.LIB))
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.search_service.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            with pytest.raises(ValueError, match="kind=code"):
                await SearchService.search_patterns("r1", "改告警")

        asyncio.run(_run())

    def test_rejects_when_no_index(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.CODE))
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.search_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.search_service.PatternVectorService.space_exists",
            AsyncMock(return_value=False),
        )

        async def _run():
            with pytest.raises(ValueError, match="尚无经验数据"):
                await SearchService.search_patterns("r1", "改告警")

        asyncio.run(_run())
