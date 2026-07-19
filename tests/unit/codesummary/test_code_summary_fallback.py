import asyncio
from unittest.mock import patch
from app.repo_analysis.services.codesummary.code_summary import CodeSummary
from app.repo_analysis.services.codesummary.model import ContentType


class TestCodeSummaryFallback:
    def test_fallback_uses_docstring_and_signature(self):
        src = '''
def extract_memory(prompt: str) -> str:
    """从对话中提取长期记忆片段。"""
    return prompt
'''
        text = CodeSummary.fallback_summary(src, ContentType.FUNCTION)
        assert "长期记忆" in text or "extract_memory" in text
        assert "签名：" in text or "功能：" in text

    def test_fallback_class_without_doc(self):
        src = "class JwtValidator:\n    def check(self):\n        return True\n"
        text = CodeSummary.fallback_summary(src, ContentType.CLASS)
        assert "JwtValidator" in text or "类" in text
        assert text.strip()

    def test_llm_error_returns_fallback(self):
        src = '''
async def think_and_act(self, question):
    """ReAct 主循环。"""
    return question
'''

        class _BadLLM:
            async def chat_stream(self, **kwargs):
                async def _gen():
                    yield "llm error: boom"

                return _gen(), None

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.code_summary.llm_factory.create_model",
                return_value=_BadLLM(),
            ):
                return await CodeSummary.llm_summarize(src, ContentType.FUNCTION)

        out = asyncio.run(_run())
        assert out
        assert "llm error" not in out.lower()
        assert "ReAct" in out or "think_and_act" in out or "功能：" in out

    def test_llm_exception_returns_fallback(self):
        src = "def foo():\n    return 1\n"

        async def _run():
            with patch(
                "app.repo_analysis.services.codesummary.code_summary.llm_factory.create_model",
                side_effect=RuntimeError("down"),
            ):
                return await CodeSummary.llm_summarize(src, ContentType.FUNCTION)

        out = asyncio.run(_run())
        assert out
        assert "foo" in out or "功能：" in out
