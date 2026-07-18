"""related 关键词扩展 UT。"""
from app.repo_analysis.services.codevector.related_keyword_expander import RelatedKeywordExpander


class TestRelatedKeywordExpander:
    def test_expand_chinese_memory(self):
        out = RelatedKeywordExpander.expand(["记忆"])
        assert "记忆" in out
        assert "memorys" in out
        assert "MemoryExtract" in out

    def test_expand_auth_aliases(self):
        out = RelatedKeywordExpander.expand(["鉴权"])
        assert "jwt_validator" in out
        assert "JWTValidator" in out
        assert "auth" not in out

    def test_noise_path(self):
        assert RelatedKeywordExpander.is_noise_path("website/src/api/paths.js")
        assert not RelatedKeywordExpander.is_noise_path("app/utils/auth/jwt_validator.py")
