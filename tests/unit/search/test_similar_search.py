from app.repo_analysis.services.codeast.model import ClassInfo, FileInfo, FunctionInfo
from app.repo_analysis.services.codechunk.code_chunk import CodeChunkService, LineTextChunk
from app.repo_analysis.services.codevector.similar_query import SimilarQueryNormalizer
from app.repo_analysis.services.codevector.similar_rerank import SimilarRerankService
from app.repo_analysis.services.search_service import SearchService


class TestSimilarQueryNormalizer:
    def test_normalize_strips_comments(self):
        code = (
            'class Foo:\n'
            '    """doc"""\n'
            '    def run(self):  # inline\n'
            '        return 1\n'
        )
        normalized = SimilarQueryNormalizer.normalize(code)
        assert '"""' not in normalized
        assert "# inline" not in normalized
        assert "def run" in normalized

    def test_extract_symbol_names(self):
        code = "class ContextBuilder:\n    async def think_and_act(self):\n        pass\n"
        names = SimilarQueryNormalizer.extract_symbol_names(code)
        assert "ContextBuilder" in names
        assert "think_and_act" in names

    def test_build_embed_queries_deduplicates(self):
        code = "def foo():\n    return 1\n"
        queries = SimilarQueryNormalizer.build_embed_queries(code)
        assert queries
        assert queries[0].strip() == code.strip()


class TestSimilarRerankService:
    def test_rerank_prefers_lexical_and_symbol_overlap(self):
        docs = [
            {
                "file_path": "a.py",
                "start_line": 1,
                "end_line": 5,
                "content": "class Noise:\n    pass\n",
                "_score": 0.95,
            },
            {
                "file_path": "b.py",
                "start_line": 10,
                "end_line": 30,
                "content": "class ContextBuilder:\n    def build(self):\n        return self.ctx\n",
                "_score": 0.70,
            },
        ]
        query = "class ContextBuilder:\n    def __init__(self, ctx):\n        self.ctx = ctx\n"
        ranked = SimilarRerankService.rerank(
            docs,
            query,
            SimilarQueryNormalizer.extract_symbol_names(query),
        )
        assert ranked[0]["file_path"] == "b.py"

    def test_dedupe_by_file_keeps_best_chunk(self):
        docs = [
            {"file_path": "svc.py", "start_line": 1, "end_line": 3, "content": "x", "_score": 0.5, "_fused_score": 0.5},
            {"file_path": "svc.py", "start_line": 4, "end_line": 8, "content": "y", "_score": 0.9, "_fused_score": 0.9},
        ]
        deduped = SimilarRerankService._dedupe_by_file(docs)
        assert len(deduped) == 1
        assert deduped[0]["start_line"] == 4


class TestSearchServiceSimilarFusion:
    def test_fuse_similar_items_applies_trim(self):
        docs = [
            {
                "file_path": "a.py",
                "start_line": 1,
                "end_line": 10,
                "content": "class SearchService:\n    pass\n",
                "_score": 0.9,
            },
            {
                "file_path": "b.py",
                "start_line": 1,
                "end_line": 2,
                "content": "print('x')\n",
                "_score": 0.1,
            },
        ]
        items = SearchService.fuse_similar_items(
            docs,
            query_text="class SearchService:\n    async def search_similar_code():\n        pass\n",
            top_k=5,
        )
        assert items
        assert items[0]["file_path"] == "a.py"
        assert items[0]["match_source"] == "line_chunk"
        assert "vector_score" in items[0]

    def test_similar_trim_raises_floor_and_caps_strong_signal(self):
        items = [
            {
                "file_path": "app/agents/core/react.py",
                "score": 1.0,
                "symbol_score": 1.0,
                "lexical_score": 0.8,
            },
            {
                "file_path": "app/agents/core/base.py",
                "score": 0.95,
                "symbol_score": 0.0,
                "lexical_score": 0.2,
            },
            {
                "file_path": "app/agents/plan/planning.py",
                "score": 0.92,
                "symbol_score": 0.0,
                "lexical_score": 0.1,
            },
            {
                "file_path": "app/other/x.py",
                "score": 0.70,
                "symbol_score": 0.0,
                "lexical_score": 0.0,
            },
        ]
        trimmed = SearchService._apply_similar_trim(
            items,
            top_k=10,
            symbol_names={"think_and_act", "ReActAgent"},
        )
        # 同目录配额 + 极强信号：只留 top1
        assert [it["file_path"] for it in trimmed] == ["app/agents/core/react.py"]
        assert len(trimmed) <= SearchService.SIMILAR_VERY_STRONG_CAP

    def test_similar_trim_dir_quota_keeps_diverse_parents(self):
        items = [
            {"file_path": "app/a/one.py", "score": 1.0, "symbol_score": 0.0, "lexical_score": 0.1},
            {"file_path": "app/a/two.py", "score": 0.99, "symbol_score": 0.0, "lexical_score": 0.1},
            {"file_path": "app/b/three.py", "score": 0.98, "symbol_score": 0.0, "lexical_score": 0.1},
            {"file_path": "app/c/four.py", "score": 0.97, "symbol_score": 0.0, "lexical_score": 0.1},
        ]
        trimmed = SearchService._apply_similar_trim(items, top_k=10, symbol_names=set())
        paths = [it["file_path"] for it in trimmed]
        assert "app/a/one.py" in paths
        assert "app/a/two.py" not in paths
        assert "app/b/three.py" in paths
        assert len(trimmed) <= SearchService.SIMILAR_SOFT_CAP


class TestCodeChunkSymbolBodies:
    def test_slice_symbol_bodies_from_ast(self):
        file_info = FileInfo(
            name="ctx.py",
            file_path="ctx.py",
            language="python",
            functions=[],
            classes=[
                ClassInfo(
                    name="ContextBuilder",
                    full_name="ctx.ContextBuilder",
                    source_code="class ContextBuilder:\n    def __init__(self, ctx):\n        self.ctx = ctx\n",
                    start_line=1,
                    end_line=3,
                    methods=[
                        FunctionInfo(
                            name="__init__",
                            full_name="ContextBuilder.__init__",
                            signature="__init__(self, ctx)",
                            type="method",
                            source_code="    def __init__(self, ctx):\n        self.ctx = ctx\n",
                            params=["self", "ctx"],
                            param_types=[],
                            returns=[],
                            return_types=[],
                            start_line=2,
                            end_line=3,
                        )
                    ],
                )
            ],
            imports=[],
        )
        symbol_chunks = CodeChunkService.slice_symbol_bodies(file_info, file_ext=".py")
        assert len(symbol_chunks) >= 1
        assert any("ContextBuilder" in c.text for c in symbol_chunks)

    def test_merge_chunks_skips_overlapping_line_windows(self):
        line_chunks = [
            LineTextChunk(1, 5, "class Foo:\n    pass\n"),
            LineTextChunk(20, 25, "def orphan():\n    return 1\n"),
        ]
        symbol_chunks = [
            LineTextChunk(1, 8, "class Foo:\n    def run(self):\n        return 1\n"),
        ]
        merged = CodeChunkService.merge_chunks(line_chunks, symbol_chunks)
        paths = [(c.start_line, c.end_line) for c in merged]
        assert (1, 8) in paths
        assert (20, 25) in paths
        assert (1, 5) not in paths
