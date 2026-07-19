"""NL→Code 查询构造 UT。"""
from app.repo_analysis.services.nl2code_enhance import NlCodeQueryBuilder
from app.repo_analysis.services.codevector.similar_query import SimilarQueryNormalizer


class TestNlCodeQueryBuilder:
    def test_looks_like_nl_chinese(self):
        assert NlCodeQueryBuilder.looks_like_nl("鉴权在哪")
        assert NlCodeQueryBuilder.looks_like_nl("记忆提取提示词")

    def test_looks_like_nl_english_phrase(self):
        q = "default memory extract prompt for agent long-term memory"
        assert NlCodeQueryBuilder.looks_like_nl(q)
        assert not NlCodeQueryBuilder._looks_like_code(q)

    def test_looks_like_nl_rejects_short_latin_ident(self):
        assert not NlCodeQueryBuilder.looks_like_nl("JWTValidator")
        assert not NlCodeQueryBuilder.looks_like_nl("jwt_validator")
        assert not NlCodeQueryBuilder.looks_like_nl("auth")
        assert NlCodeQueryBuilder.looks_like_nl("JWT auth location")

    def test_build_embed_queries_chinese_instruct_only(self):
        qs = NlCodeQueryBuilder.build_embed_queries("鉴权在哪")
        joined = "\n".join(qs)
        assert "鉴权在哪" in qs[0]
        assert "Instruct:" in joined
        assert "jwt_validator" not in joined
        assert "JWTValidator" not in joined

    def test_build_embed_queries_latin_morph_and_hyde(self):
        qs = NlCodeQueryBuilder.build_embed_queries("JWTValidator location")
        joined = "\n".join(qs)
        assert "jwt_validator" in joined
        assert "Instruct:" in joined
        assert "def " in joined

    def test_build_embed_queries_english_phrase_tokens(self):
        qs = NlCodeQueryBuilder.build_embed_queries(
            "default memory extract prompt for agent long-term memory"
        )
        joined = "\n".join(qs)
        assert "memory" in joined.lower()
        assert "memorys" not in joined
        assert "MemoryExtract" not in joined

    def test_hyde_snake(self):
        snip = NlCodeQueryBuilder.build_hyde_snippet("JWTValidator")
        assert "jwt_validator" in snip
        assert "def jwt_validator" in snip

    def test_hyde_snippets_multilang(self):
        snips = NlCodeQueryBuilder.build_hyde_snippets("JWTValidator")
        joined = "\n".join(snips)
        assert "def jwt_validator" in joined
        assert "function jwt_validator" in joined
        assert "jwt_validator(" in joined


class TestSimilarQueryNormalizerNlBranch:
    def test_nl_query_uses_nl_builder(self):
        qs = SimilarQueryNormalizer.build_embed_queries("鉴权在哪")
        assert qs and qs[0] == "鉴权在哪"
        assert any(q.startswith("Instruct:") for q in qs)
        assert not any("jwt_validator" in q for q in qs)

    def test_code_query_keeps_code_path(self):
        code = "def foo():\n    return 1\n"
        qs = SimilarQueryNormalizer.build_embed_queries(code)
        assert qs[0].strip() == code.strip()
        assert not any(q.startswith("Instruct:") for q in qs)
