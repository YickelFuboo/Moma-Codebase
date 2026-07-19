"""仓内 identifier lexicon UT。"""
from app.repo_analysis.services.nl2code_enhance import RelatedKeywordExpander, RepoIdentifierLexicon


class TestRepoIdentifierLexicon:
    def test_from_paths_extracts_stems(self):
        lex = RepoIdentifierLexicon.from_paths(
            [
                "app/agents/memorys/default/memory.py",
                "app/utils/auth/jwt_validator.py",
                "app/websocket/manager.py",
            ]
        )
        folds = {x.casefold() for x in lex._idents}
        assert "memorys" in folds
        assert "jwt_validator" in folds or "jwt" in folds
        assert "websocket" in folds

    def test_expand_memory_to_memorys(self):
        lex = RepoIdentifierLexicon.from_paths(["app/agents/memorys/default/memory.py"])
        hits = lex.expand_tokens(["memory"])
        assert any(h.casefold() == "memorys" for h in hits)

    def test_expand_with_lexicon_vs_without(self):
        lex = RepoIdentifierLexicon.from_paths(
            ["app/utils/auth/jwt_validator.py", "app/agents/memorys/memory.py"]
        )
        without = RelatedKeywordExpander.expand(["memory extract"])
        with_lex = RelatedKeywordExpander.expand(["memory extract"], lexicon=lex)
        assert "memorys" not in without
        assert any(x.casefold() == "memorys" for x in with_lex)

    def test_chinese_not_mapped_via_path_lexicon(self):
        lex = RepoIdentifierLexicon.from_paths(["app/utils/auth/jwt_validator.py"])
        out = RelatedKeywordExpander.expand(["鉴权"], lexicon=lex)
        assert "鉴权" in out
        assert "jwt_validator" not in out

    def test_expand_rejects_short_prefix_reverse_match(self):
        """短 ident 不应因 sf.startswith(inf) 误扩到无关长名。"""
        lex = RepoIdentifierLexicon.from_paths(
            [
                "app/auth/jwt_validator.py",
                "app/utils/json_helper.py",
            ]
        )
        hits = {h.casefold() for h in lex.expand_tokens(["json"])}
        assert "json_helper" in hits or "json" in hits
        assert "jwt_validator" not in hits

    def test_cache_clear_removes_entry(self):
        RepoIdentifierLexicon.cache_clear()
        lex = RepoIdentifierLexicon.from_paths(["app/foo/bar.py"])
        RepoIdentifierLexicon.cache_put("repo-x", lex)
        assert RepoIdentifierLexicon.cache_get("repo-x") is lex
        RepoIdentifierLexicon.cache_clear("repo-x")
        assert RepoIdentifierLexicon.cache_get("repo-x") is None
