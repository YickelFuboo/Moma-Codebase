import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.cli.search import _assert_kind_code, _assert_kind_lib
from app.lib_analysis.services.search_service import LibSearchService
from app.repo_mgmt.models.git_repo_mgmt import RepoKind


class _Repo:
    def __init__(self, kind: str, repo_id: str = "r1"):
        self.kind = kind
        self.id = repo_id


class TestCliKindGuards:
    def test_assert_kind_code_rejects_lib(self):
        import click

        with pytest.raises(click.ClickException, match="kind=code"):
            _assert_kind_code(_Repo(RepoKind.LIB))

    def test_assert_kind_lib_rejects_code(self):
        import click

        with pytest.raises(click.ClickException, match="kind=lib"):
            _assert_kind_lib(_Repo(RepoKind.CODE))

    def test_assert_kind_ok(self):
        _assert_kind_code(_Repo(RepoKind.CODE))
        _assert_kind_lib(_Repo(RepoKind.LIB))


class TestLibSearchServiceGuards:
    def test_empty_query(self):
        async def _run():
            with pytest.raises(ValueError, match="query"):
                await LibSearchService.search_apis("r1", "  ")

        asyncio.run(_run())

    def test_rejects_code_kind(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.CODE))
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.lib_analysis.services.search_service.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            with pytest.raises(ValueError, match="kind=lib"):
                await LibSearchService.search_apis("r1", "打开文件")

        asyncio.run(_run())

    def test_rejects_missing_repo(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=None)
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.lib_analysis.services.search_service.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            with pytest.raises(ValueError, match="仓库不存在"):
                await LibSearchService.search_apis("missing", "q")

        asyncio.run(_run())

    def test_rejects_when_index_missing(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.LIB))
                return db

            async def __aexit__(self, *args):
                return False

        class _Model:
            async def encode(self, texts):
                return [[0.1, 0.2, 0.3]], None

        monkeypatch.setattr(
            "app.lib_analysis.services.search_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.lib_analysis.services.search_service.embedding_factory.create_model",
            lambda: _Model(),
        )
        monkeypatch.setattr(
            "app.lib_analysis.services.search_service.VECTOR_STORE_CONN.space_exists",
            AsyncMock(return_value=False),
        )

        async def _run():
            with pytest.raises(ValueError, match="尚未完成分析"):
                await LibSearchService.search_apis("r1", "打开文件")

        asyncio.run(_run())
