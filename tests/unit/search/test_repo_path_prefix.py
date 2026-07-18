from types import SimpleNamespace
from app.repo_mgmt.services.repo_resolver import RepoResolver


class TestRepoPathPrefixMatch:
    def test_exact_match(self, tmp_path):
        root = tmp_path / "a" / "b" / "c" / "d"
        root.mkdir(parents=True)
        assert RepoResolver.is_path_prefix_match(str(root), str(root))

    def test_parent_matches_children(self, tmp_path):
        d = tmp_path / "a" / "b" / "c" / "d"
        e = tmp_path / "a" / "b" / "c" / "e"
        f = tmp_path / "a" / "b" / "f"
        for p in (d, e, f):
            p.mkdir(parents=True)
        parent_c = tmp_path / "a" / "b" / "c"
        parent_b = tmp_path / "a" / "b"
        assert RepoResolver.is_path_prefix_match(str(parent_c), str(d))
        assert RepoResolver.is_path_prefix_match(str(parent_c), str(e))
        assert not RepoResolver.is_path_prefix_match(str(parent_c), str(f))
        assert RepoResolver.is_path_prefix_match(str(parent_b), str(d))
        assert RepoResolver.is_path_prefix_match(str(parent_b), str(e))
        assert RepoResolver.is_path_prefix_match(str(parent_b), str(f))

    def test_sibling_not_matched(self, tmp_path):
        d = tmp_path / "a" / "b" / "c" / "d"
        other = tmp_path / "a" / "b2" / "c"
        d.mkdir(parents=True)
        other.mkdir(parents=True)
        assert not RepoResolver.is_path_prefix_match(str(tmp_path / "a" / "b" / "c"), str(other))

    def test_expand_search_paths_union(self, tmp_path):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        d = tmp_path / "a" / "b" / "c" / "d"
        e = tmp_path / "a" / "b" / "c" / "e"
        f = tmp_path / "a" / "b" / "f"
        for p in (d, e, f):
            p.mkdir(parents=True)
        repos = [
            SimpleNamespace(id="1", local_path=str(d), user_id="default"),
            SimpleNamespace(id="2", local_path=str(e), user_id="default"),
            SimpleNamespace(id="3", local_path=str(f), user_id="default"),
        ]

        async def _run():
            db = MagicMock()
            result = MagicMock()
            result.scalars.return_value.all.return_value = repos
            db.execute = AsyncMock(return_value=result)
            got = await RepoResolver.expand_search_paths(
                db,
                [str(tmp_path / "a" / "b" / "c")],
                user_id="default",
            )
            assert {r.id for r in got} == {"1", "2"}
            got2 = await RepoResolver.expand_search_paths(
                db,
                [str(tmp_path / "a" / "b")],
                user_id="default",
            )
            assert {r.id for r in got2} == {"1", "2", "3"}
            got3 = await RepoResolver.expand_search_paths(
                db,
                [str(d), str(f)],
                user_id="default",
            )
            assert {r.id for r in got3} == {"1", "3"}

        asyncio.run(_run())

    def test_expand_search_paths_filters_by_kind(self, tmp_path):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        code_d = tmp_path / "a" / "b" / "c" / "d"
        lib_e = tmp_path / "a" / "b" / "c" / "e"
        code_f = tmp_path / "a" / "b" / "f"
        for p in (code_d, lib_e, code_f):
            p.mkdir(parents=True)
        repos = [
            SimpleNamespace(id="1", local_path=str(code_d), user_id="default", kind="code"),
            SimpleNamespace(id="2", local_path=str(lib_e), user_id="default", kind="lib"),
            SimpleNamespace(id="3", local_path=str(code_f), user_id="default", kind="code"),
        ]

        async def _run():
            db = MagicMock()
            result = MagicMock()
            result.scalars.return_value.all.return_value = repos
            db.execute = AsyncMock(return_value=result)
            parent = str(tmp_path / "a" / "b")
            code_only = await RepoResolver.expand_search_paths(
                db, [parent], user_id="default", kind="code"
            )
            assert {r.id for r in code_only} == {"1", "3"}
            lib_only = await RepoResolver.expand_search_paths(
                db, [parent], user_id="default", kind="lib"
            )
            assert {r.id for r in lib_only} == {"2"}
            both = await RepoResolver.expand_search_paths(
                db, [parent], user_id="default"
            )
            assert {r.id for r in both} == {"1", "2", "3"}

        asyncio.run(_run())
