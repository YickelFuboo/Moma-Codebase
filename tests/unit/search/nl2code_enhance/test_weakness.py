"""NL 检索弱判定 UT。"""
from app.repo_analysis.services.nl2code_enhance.weakness import NlRetrievalWeakness
from app.repo_analysis.services.search_resolve.intent import SearchIntent
from app.repo_analysis.services.search_resolve.weak_fallback import ResolveWeakFallback


class TestNlRetrievalWeakness:
    def test_empty_is_weak(self):
        assert NlRetrievalWeakness.is_score_weak([])
        assert NlRetrievalWeakness.needs_nl_rewrite([])

    def test_exact_not_weak(self):
        items = [{"match_source": "exact", "score": 0.1}]
        assert not NlRetrievalWeakness.is_score_weak(items)
        assert not NlRetrievalWeakness.needs_nl_rewrite(items)

    def test_nl_token_hit_skips_rewrite(self):
        items = [{"score": 0.2, "nl_token_hit": True}]
        assert NlRetrievalWeakness.is_score_weak(items)
        assert not NlRetrievalWeakness.needs_nl_rewrite(items)

    def test_shared_threshold_with_channel_fallback(self):
        weak_items = [{"match_source": "line_chunk", "score": 0.5}]
        strong_items = [{"match_source": "line_chunk", "score": 0.9}]
        assert NlRetrievalWeakness.needs_nl_rewrite(weak_items)
        assert NlRetrievalWeakness.needs_channel_fallback(SearchIntent.RELATED, weak_items)
        assert ResolveWeakFallback.is_weak(SearchIntent.RELATED, weak_items)
        assert not NlRetrievalWeakness.needs_nl_rewrite(strong_items)
        assert not ResolveWeakFallback.is_weak(SearchIntent.RELATED, strong_items)
        assert NlRetrievalWeakness.WEAK_SCORE_THRESHOLD == ResolveWeakFallback.WEAK_SCORE_THRESHOLD
