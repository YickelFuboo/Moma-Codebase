import asyncio
import os
from app.infrastructure.vector_store.lance_conn import LanceDBConnection


def _vec4() -> list[float]:
    return [0.1, 0.2, 0.3, 0.4]


class TestLanceGhostSpace:
    """table_names 截断/漏列时，仍应能发现/读写/清理磁盘上的表。"""

    def _new_conn(self, tmp_path) -> LanceDBConnection:
        return LanceDBConnection(str(tmp_path / "lancedb"))

    def _seed(self, conn: LanceDBConnection, space: str) -> None:
        async def _run() -> None:
            assert await conn.create_space(space, 4)
            failed = await conn.insert_records(
                space,
                [
                    {
                        "id": "r1",
                        "repo_id": "repo-x",
                        "file_path": "a.py",
                        "analysis_type": "symbol_summary_vector",
                        "symbol_name": "ReActAgent",
                        "symbol_kind": "class",
                        "start_line": 1,
                        "end_line": 10,
                        "summary": "agent",
                        "q_4_vec": _vec4(),
                    }
                ],
            )
            assert failed == []

        asyncio.run(_run())

    def test_table_names_paginates_beyond_default_limit(self, tmp_path, monkeypatch):
        """LanceDB 默认 limit=10；我们的 _table_names 必须翻页取全量。"""
        conn = self._new_conn(tmp_path)
        monkeypatch.setattr(conn, "TABLE_NAMES_PAGE_SIZE", 10)
        calls = {"n": 0}

        def _paged(page_token=None, limit=10):
            calls["n"] += 1
            all_names = [f"t{i:02d}" for i in range(25)]
            start = 0
            if page_token is not None:
                start = all_names.index(page_token) + 1
            return all_names[start : start + limit]

        monkeypatch.setattr(conn.db, "table_names", _paged)
        names = conn._table_names()
        assert len(names) == 25
        assert names[0] == "t00"
        assert names[-1] == "t24"
        assert calls["n"] >= 2

    def test_space_exists_when_catalog_misses(self, tmp_path, monkeypatch):
        conn = self._new_conn(tmp_path)
        space = "repo_ghost_symbol_summary_4"
        self._seed(conn, space)
        assert space in conn._table_names()
        monkeypatch.setattr(conn, "_table_names", lambda: [])
        assert asyncio.run(conn.space_exists(space)) is True

    def test_list_records_when_catalog_misses(self, tmp_path, monkeypatch):
        conn = self._new_conn(tmp_path)
        space = "repo_ghost_list_4"
        self._seed(conn, space)
        monkeypatch.setattr(conn, "_table_names", lambda: [])
        rows = asyncio.run(
            conn.list_records(
                space,
                condition={"repo_id": "repo-x"},
                select_fields=["file_path", "symbol_name"],
                limit=10,
            )
        )
        assert len(rows) == 1
        assert rows[0]["symbol_name"] == "ReActAgent"

    def test_delete_space_removes_orphan_dir(self, tmp_path, monkeypatch):
        conn = self._new_conn(tmp_path)
        space = "repo_ghost_delete_4"
        self._seed(conn, space)
        space_dir = conn._space_dir(space)
        assert os.path.isdir(space_dir)
        monkeypatch.setattr(conn, "_table_names", lambda: [])
        assert asyncio.run(conn.delete_space(space)) is True
        assert not os.path.isdir(space_dir)
        assert asyncio.run(conn.space_exists(space)) is False
