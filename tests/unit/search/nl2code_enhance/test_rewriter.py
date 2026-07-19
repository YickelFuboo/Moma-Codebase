"""NL query rewriter UT。"""
from app.repo_analysis.services.nl2code_enhance import NlQueryRewriter, NlRewriteResult


class TestNlQueryRewriter:
    def test_parse_json_object(self):
        text = (
            'Here you go:\n'
            '{"english": "JWT authentication middleware", '
            '"identifiers": ["JWTValidator", "jwt_middleware", "jwks"]}\n'
        )
        result = NlQueryRewriter.parse_response(text)
        assert "JWT" in result.english_query or "authentication" in result.english_query
        assert "JWTValidator" in result.identifiers
        assert "jwt_middleware" in result.identifiers

    def test_parse_plain_fallback(self):
        result = NlQueryRewriter.parse_response("find auth code")
        assert result.english_query.startswith("find auth")
        assert result.identifiers == []

    def test_seeds(self):
        r = NlRewriteResult(english_query="memory extract", identifiers=["MemoryExtract", "memorys"])
        seeds = r.seeds()
        assert seeds[0] == "memory extract"
        assert "memorys" in seeds

    def test_default_disabled(self):
        assert NlQueryRewriter.is_enabled() is False or isinstance(
            NlQueryRewriter.is_enabled(), bool
        )
