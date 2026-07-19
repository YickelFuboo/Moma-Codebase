"""NlQueryPrep 门面正确性 UT。"""
from __future__ import annotations
import asyncio
from app.repo_analysis.services.nl2code_enhance.prep import NlQueryPrep
from app.repo_analysis.services.nl2code_enhance.rewriter import NlRewriteResult


async def _async_none():
    return None


class TestNlQueryPrep:
    def test_prepare_keeps_original_in_embed_when_rewritten(self, monkeypatch):
        async def _fake_rewrite(query: str):
            return NlRewriteResult(
                english_query="JWT authentication",
                identifiers=["JWTValidator"],
            )

        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlToCodeEnhancement.is_enabled",
            classmethod(lambda cls: True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.gate.NlToCodeEnhancement.is_enabled",
            classmethod(lambda cls: True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlQueryRewriter.should_rewrite_upfront",
            classmethod(lambda cls, q: True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlQueryRewriter.rewrite",
            staticmethod(_fake_rewrite),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlToCodeEnhancement.lexicon_for_repo",
            classmethod(lambda cls, repo_id: _async_none()),
        )

        prep = asyncio.run(NlQueryPrep.prepare("repo", "鉴权在哪", rewrite="auto"))
        joined = "\n".join(prep.embed_queries)
        assert prep.original_query == "鉴权在哪"
        assert any("鉴权在哪" == q or q.endswith("鉴权在哪") for q in prep.embed_queries)
        assert "JWT" in joined or "jwt" in joined.lower()
        assert prep.rewrite is not None
        assert prep.rewrite_trigger == "always"

    def test_prepare_skip_does_not_call_rewrite(self, monkeypatch):
        called = {"n": 0}

        async def _fake_rewrite(query: str):
            called["n"] += 1
            return NlRewriteResult(english_query="x", identifiers=["Y"])

        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlToCodeEnhancement.is_enabled",
            classmethod(lambda cls: True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.gate.NlToCodeEnhancement.is_enabled",
            classmethod(lambda cls: True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlQueryRewriter.rewrite",
            staticmethod(_fake_rewrite),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlToCodeEnhancement.lexicon_for_repo",
            classmethod(lambda cls, repo_id: _async_none()),
        )

        prep = asyncio.run(NlQueryPrep.prepare("repo", "鉴权在哪", rewrite="skip"))
        assert called["n"] == 0
        assert prep.rewrite is None
        assert any("鉴权在哪" in q for q in prep.embed_queries)

    def test_prepare_with_provided_rewrite_does_not_call_llm(self, monkeypatch):
        called = {"n": 0}

        async def _fake_rewrite(query: str):
            called["n"] += 1
            return NlRewriteResult(english_query="should-not", identifiers=[])

        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlToCodeEnhancement.is_enabled",
            classmethod(lambda cls: True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.gate.NlToCodeEnhancement.is_enabled",
            classmethod(lambda cls: True),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlQueryRewriter.rewrite",
            staticmethod(_fake_rewrite),
        )
        monkeypatch.setattr(
            "app.repo_analysis.services.nl2code_enhance.prep.NlToCodeEnhancement.lexicon_for_repo",
            classmethod(lambda cls, repo_id: _async_none()),
        )

        given = NlRewriteResult(english_query="JWT auth", identifiers=["jwt_middleware"])
        prep = asyncio.run(
            NlQueryPrep.prepare(
                "repo",
                "鉴权在哪",
                rewrite="skip",
                rewrite_result=given,
                rewrite_trigger="always",
            )
        )
        assert called["n"] == 0
        assert prep.rewrite is given
        assert "jwt_middleware" in "\n".join(prep.embed_queries).lower() or any(
            "jwt" in k.lower() for k in prep.keywords
        )
