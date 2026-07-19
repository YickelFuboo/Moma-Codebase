"""NL→Code 检索增强总开关 UT。"""
from app.config.settings import settings
from app.repo_analysis.services.nl2code_enhance import NlQueryRewriter, NlToCodeEnhancement
from app.repo_analysis.services.codevector.similar_query import SimilarQueryNormalizer


class TestNlToCodeEnhancementGate:
    def test_default_enabled(self):
        assert NlToCodeEnhancement.is_enabled() is True

    def test_disabled_skips_nl_embed_branch(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_nl_to_code_enabled", False)
        qs = SimilarQueryNormalizer.build_embed_queries("鉴权在哪")
        assert qs == ["鉴权在哪"]
        assert not any(q.startswith("Instruct:") for q in qs)

    def test_disabled_blocks_rewrite_even_if_rewrite_flag_on(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_nl_to_code_enabled", False)
        monkeypatch.setattr(settings, "code_analysis_nl_rewrite_enabled", True)
        assert NlQueryRewriter.is_enabled() is False

    def test_enabled_allows_nl_embed_branch(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_nl_to_code_enabled", True)
        qs = SimilarQueryNormalizer.build_embed_queries("鉴权在哪")
        assert qs and qs[0] == "鉴权在哪"
        assert any(q.startswith("Instruct:") for q in qs)
