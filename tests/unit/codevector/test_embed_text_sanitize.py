from app.repo_analysis.services.codechunk.code_chunk import LineTextChunk


class TestEmbedTextSourceFilter:
    def test_line_chunks_skip_empty_before_texts(self):
        chunks = [
            LineTextChunk(text="def ok():\n    return 1\n", start_line=1, end_line=2),
            LineTextChunk(text="   \n", start_line=3, end_line=3),
            LineTextChunk(text="", start_line=4, end_line=4),
            LineTextChunk(text="class A:\n    pass\n", start_line=5, end_line=6),
        ]
        kept = [c for c in chunks if str(c.text or "").strip()]
        texts = [c.text for c in kept]
        assert len(texts) == 2
        assert all(str(t).strip() for t in texts)

    def test_symbol_embed_skip_empty_summary(self):
        summaries = ["有内容", "", "  "]
        texts = []
        for s in summaries:
            t = (s or "").strip()
            if not t:
                continue
            texts.append(t)
        assert texts == ["有内容"]
