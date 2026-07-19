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

    def test_expand_english_memory_phrase(self):
        out = RelatedKeywordExpander.expand(
            ["default memory extract prompt for agent long-term memory"]
        )
        assert "memorys" in out or "MemoryExtract" in out
        assert any("memory" in x.lower() for x in out)

    def test_core_tokens_skips_stopwords(self):
        toks = RelatedKeywordExpander.core_tokens(
            "default memory extract prompt for agent long-term memory"
        )
        assert "memory" in toks
        assert "extract" in toks
        assert "default" not in [t.lower() for t in toks]
        assert "agent" not in [t.lower() for t in toks]

    def test_core_tokens_drops_generic_when_specific_exists(self):
        toks = RelatedKeywordExpander.core_tokens(
            "websocket channel connection manager for realtime messages"
        )
        lower = [t.lower() for t in toks]
        assert "websocket" in lower
        assert "manager" not in lower
        assert "connection" not in lower
        assert "realtime" not in lower
        assert "channel" not in lower
