"""related 关键词扩展 UT。"""
from app.repo_analysis.services.nl2code_enhance import RelatedKeywordExpander


class TestRelatedKeywordExpander:
    def test_expand_chinese_keeps_original(self):
        out = RelatedKeywordExpander.expand(["记忆"])
        assert "记忆" in out
        assert "memorys" not in out
        assert "MemoryExtract" not in out

    def test_expand_chinese_auth_no_latin_idents(self):
        out = RelatedKeywordExpander.expand(["鉴权"])
        assert "鉴权" in out
        assert "jwt_validator" not in out
        assert "JWTValidator" not in out

    def test_expand_english_morphology(self):
        out = RelatedKeywordExpander.expand(["JWTValidator"])
        assert "JWTValidator" in out
        assert "jwt_validator" in out

    def test_expand_english_phrase_tokens(self):
        out = RelatedKeywordExpander.expand(
            ["default memory extract prompt for agent long-term memory"]
        )
        assert "memory" in [x.lower() for x in out]
        assert "extract" in [x.lower() for x in out]
        assert "memorys" not in out
        assert "MemoryExtract" not in out

    def test_core_tokens_skips_stopwords(self):
        toks = RelatedKeywordExpander.core_tokens(
            "default memory extract prompt for agent long-term memory"
        )
        assert "memory" in toks
        assert "extract" in toks
        assert "default" not in [t.lower() for t in toks]
        assert "agent" not in [t.lower() for t in toks]

    def test_path_matches_tokens_latin(self):
        assert RelatedKeywordExpander.path_matches_tokens(
            "app/utils/auth/jwt_validator.py",
            ["jwt_validator location"],
        )
        assert not RelatedKeywordExpander.path_matches_tokens(
            "app/utils/auth/jwt_validator.py",
            ["鉴权在哪"],
        )
        assert not RelatedKeywordExpander.path_matches_tokens(
            "app/config/settings.py",
            ["jwt_validator"],
        )

    def test_is_noise_path_uses_generic_dirs(self):
        assert RelatedKeywordExpander.is_noise_path("node_modules/pkg/index.js")
        assert RelatedKeywordExpander.is_noise_path("app/.venv/lib/site.py")
        assert not RelatedKeywordExpander.is_noise_path("app/utils/auth/jwt.py")
        assert not RelatedKeywordExpander.is_noise_path("website/pages/index.tsx")
