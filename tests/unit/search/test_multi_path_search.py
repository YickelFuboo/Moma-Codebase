import asyncio
from app.repo_analysis.services.multi_path_search import MultiPathSearchService


class TestMultiPathSearchService:
    def test_normalize_paths_dedupes(self):
        paths = MultiPathSearchService.normalize_paths(
            [r"F:\a\repo", r"F:\a\repo/", r"F:\b\repo", ""]
        )
        assert len(paths) == 2
        assert paths[0].replace("\\", "/").rstrip("/").lower().endswith("a/repo")

    def test_merge_items_keeps_cross_repo_same_relpath(self):
        batches = [
            [
                {
                    "repo_id": "r1",
                    "path": r"F:\front",
                    "file_path": "src/auth.ts",
                    "score": 2.0,
                    "match_source": "exact",
                    "exact_tier": "symbol",
                }
            ],
            [
                {
                    "repo_id": "r2",
                    "path": r"F:\back",
                    "file_path": "src/auth.ts",
                    "score": 3.0,
                    "match_source": "exact",
                    "exact_tier": "symbol",
                }
            ],
        ]
        merged = MultiPathSearchService.merge_items(batches, top_k=10)
        assert len(merged) == 2
        assert {m["repo_id"] for m in merged} == {"r1", "r2"}

    def test_merge_items_prefers_stronger_source(self):
        batches = [
            [
                {
                    "repo_id": "r1",
                    "path": r"F:\a",
                    "file_path": "a.py",
                    "score": 9.0,
                    "match_source": "codegraph",
                },
                {
                    "repo_id": "r1",
                    "path": r"F:\a",
                    "file_path": "a.py",
                    "score": 1.0,
                    "match_source": "exact",
                    "exact_tier": "symbol",
                },
            ]
        ]
        merged = MultiPathSearchService.merge_items(batches, top_k=5)
        assert len(merged) == 1
        assert merged[0]["match_source"] == "exact"

    def test_merge_search_payloads_multi(self):
        payloads = [
            {
                "path": r"F:\front",
                "repo_id": "r1",
                "kind": "code",
                "intent": "related",
                "channels_used": ["related"],
                "total": 1,
                "items": [
                    {
                        "file_path": "web/login.ts",
                        "score": 2.0,
                        "match_source": "exact",
                        "exact_tier": "symbol",
                    }
                ],
            },
            {
                "path": r"F:\back",
                "repo_id": "r2",
                "kind": "code",
                "intent": "related",
                "channels_used": ["related"],
                "total": 1,
                "items": [
                    {
                        "file_path": "api/auth.py",
                        "score": 1.5,
                        "match_source": "exact",
                        "exact_tier": "symbol",
                    }
                ],
            },
        ]
        out = MultiPathSearchService.merge_search_payloads(
            payloads,
            top_k=5,
            query_fields={"query": "auth"},
        )
        assert out["paths"] == [r"F:\front", r"F:\back"]
        assert out["total"] == 2
        assert out["query"] == "auth"
        assert out["intent"] == "related"
        assert all("path" in it and "repo_id" in it for it in out["items"])

    def test_merge_search_payloads_single_keeps_shape(self):
        payloads = [
            {
                "path": r"F:\only",
                "repo_id": "r1",
                "kind": "code",
                "total": 1,
                "items": [{"file_path": "a.py", "score": 1.0}],
            }
        ]
        out = MultiPathSearchService.merge_search_payloads(payloads, top_k=5)
        assert out["path"] == r"F:\only"
        assert out["paths"] == [r"F:\only"]
        assert out["total"] == 1

    def test_fanout_aggregates_errors(self):
        async def _run():
            async def _one(path: str):
                if path.endswith("bad"):
                    raise RuntimeError("boom")
                return {
                    "path": path,
                    "repo_id": "ok",
                    "kind": "code",
                    "total": 1,
                    "items": [
                        {
                            "file_path": "ok.py",
                            "score": 2.0,
                            "match_source": "exact",
                            "exact_tier": "symbol",
                        }
                    ],
                }

            return await MultiPathSearchService.fanout(
                [r"F:\good", r"F:\bad"],
                top_k=5,
                run_one=_one,
            )

        out = asyncio.run(_run())
        assert out["total"] == 1
        assert "repo_errors" in out
        assert any("boom" in v for v in out["repo_errors"].values())
