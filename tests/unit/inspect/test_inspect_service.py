import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.repo_analysis.services.inspect_service import InspectService
from app.repo_mgmt.models.git_repo_mgmt import RepoKind


class _Repo:
    def __init__(self, kind: str, repo_id: str = "r1"):
        self.kind = kind
        self.id = repo_id


class TestPathHelpers:
    def test_normalize_target_empty(self):
        assert InspectService.normalize_target(None) is None
        assert InspectService.normalize_target("  ") is None
        assert InspectService.normalize_target("/") is None

    def test_normalize_target_strips(self):
        assert InspectService.normalize_target(" app/cli/ ") == "app/cli"

    def test_match_path_all(self):
        assert InspectService.match_path("a/b.py", None) is True

    def test_match_path_exact_and_prefix(self):
        assert InspectService.match_path("app/cli/main.py", "app/cli/main.py") is True
        assert InspectService.match_path("app/cli/main.py", "app/cli") is True
        assert InspectService.match_path("app/cli2/main.py", "app/cli") is False
        assert InspectService.match_path("app/cli", "app/cli") is True

    def test_apply_limit(self):
        items = [{"i": i} for i in range(10)]
        assert len(InspectService.apply_limit(items, 3)) == 3
        assert len(InspectService.apply_limit(items, 0)) == 10
        assert len(InspectService.apply_limit(items, -1)) == 10


class TestWriteExport:
    def test_write_export_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out", "inspect.json")
            written = InspectService.write_export({"total": 1, "items": []}, path)
            assert os.path.isfile(written)
            with open(written, encoding="utf-8") as f:
                data = json.load(f)
            assert data["total"] == 1


class TestInspectServiceGuards:
    def test_chunks_rejects_lib(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.LIB))
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            with pytest.raises(ValueError, match="kind=code"):
                await InspectService.inspect_chunks("r1")

        asyncio.run(_run())

    def test_apis_rejects_code(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.CODE))
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.get_db_session",
            lambda: _CM(),
        )

        async def _run():
            with pytest.raises(ValueError, match="kind=lib"):
                await InspectService.inspect_apis("r1")

        asyncio.run(_run())

    def test_chunks_missing_space(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.CODE))
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            InspectService,
            "_embedding_dim",
            staticmethod(AsyncMock(return_value=8)),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.VECTOR_STORE_CONN.space_exists",
            AsyncMock(return_value=False),
        )

        async def _run():
            with pytest.raises(ValueError, match="切片向量"):
                await InspectService.inspect_chunks("r1")

        asyncio.run(_run())

    def test_apis_missing_space(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.LIB))
                return db

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            InspectService,
            "_embedding_dim",
            staticmethod(AsyncMock(return_value=8)),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.VECTOR_STORE_CONN.space_exists",
            AsyncMock(return_value=False),
        )

        async def _run():
            with pytest.raises(ValueError, match="API 向量"):
                await InspectService.inspect_apis("r1")

        asyncio.run(_run())


class TestInspectChunksFilter:
    def test_filter_target_and_limit(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.CODE))
                return db

            async def __aexit__(self, *args):
                return False

        rows = [
            {
                "file_path": "app/a.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_index": 0,
                "content": "aaa",
            },
            {
                "file_path": "app/cli/b.py",
                "start_line": 1,
                "end_line": 5,
                "chunk_index": 0,
                "content": "bbb" * 100,
            },
            {
                "file_path": "app/cli/c.py",
                "start_line": 2,
                "end_line": 6,
                "chunk_index": 1,
                "content": "ccc",
            },
        ]
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            InspectService,
            "_embedding_dim",
            staticmethod(AsyncMock(return_value=8)),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.VECTOR_STORE_CONN.space_exists",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.VECTOR_STORE_CONN.list_records",
            AsyncMock(return_value=rows),
        )

        async def _run():
            data = await InspectService.inspect_chunks(
                "r1",
                target="app/cli",
                limit=1,
                full_content=False,
            )
            assert data["matched_before_limit"] == 2
            assert data["total"] == 1
            assert data["items"][0]["file_path"] == "app/cli/b.py"
            assert "content_preview" in data["items"][0]
            assert "content" not in data["items"][0]
            assert len(data["items"][0]["content_preview"]) <= InspectService.CONTENT_PREVIEW_LEN

            full = await InspectService.inspect_chunks(
                "r1",
                target="app/cli/b.py",
                limit=10,
                full_content=True,
            )
            assert full["total"] == 1
            assert full["items"][0]["content"] == "bbb" * 100

        asyncio.run(_run())


class TestInspectApisFilter:
    def test_filter_file_and_limit(self, monkeypatch):
        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.LIB))
                return db

            async def __aexit__(self, *args):
                return False

        rows = [
            {
                "file_path": "pkg/a.py",
                "symbol_kind": "function",
                "symbol_name": "foo",
                "content": "def foo()",
                "summary": "s1",
                "start_line": 1,
                "end_line": 2,
            },
            {
                "file_path": "pkg/b.py",
                "symbol_kind": "class",
                "symbol_name": "Bar",
                "content": "class Bar",
                "summary": "s2",
                "start_line": 1,
                "end_line": 3,
            },
        ]
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            InspectService,
            "_embedding_dim",
            staticmethod(AsyncMock(return_value=8)),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.VECTOR_STORE_CONN.space_exists",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.VECTOR_STORE_CONN.list_records",
            AsyncMock(return_value=rows),
        )

        async def _run():
            data = await InspectService.inspect_apis("r1", file_path="pkg/b.py", limit=5)
            assert data["total"] == 1
            assert data["items"][0]["api_name"] == "Bar"
            assert data["items"][0]["api_kind"] == "class"

        asyncio.run(_run())


class TestInspectGraph:
    def test_graph_limit_and_query(self, monkeypatch):
        class _Scalars:
            def all(self):
                return ["app/a.py", "app/b.py", "other/c.py"]

        class _CM:
            async def __aenter__(self):
                db = MagicMock()
                db.scalar = AsyncMock(return_value=_Repo(RepoKind.CODE))
                db.scalars = AsyncMock(return_value=_Scalars())
                return db

            async def __aexit__(self, *args):
                return False

        class _Resp:
            def __init__(self, ok, content, message=""):
                self.result = ok
                self.content = content
                self.message = message

        class _Search:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            async def query_dependented_of_file(self, repo_id, file_path):
                return _Resp(True, {"dependented": [f"dep/{file_path}"]})

            async def query_dependents_of_file(self, repo_id, file_path):
                return _Resp(True, {"dependents": [f"use/{file_path}"]})

        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.get_db_session",
            lambda: _CM(),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.inspect_service.CodeGraphGateway.create_search",
            staticmethod(lambda: _Search()),
        )

        async def _run():
            data = await InspectService.inspect_graph("r1", target="app", limit=1)
            assert data["total"] == 1
            assert data["files"][0]["file_path"] == "app/a.py"
            assert data["files"][0]["dependencies"] == ["dep/app/a.py"]
            assert data["files"][0]["dependents"] == ["use/app/a.py"]

        asyncio.run(_run())
