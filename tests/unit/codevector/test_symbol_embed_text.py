"""符号向量入库文本 UT：文件 + 符号 + 摘要，不含路径切词。"""
from app.repo_analysis.services.codevector.code_vector import CodeVectorService


class TestSymbolEmbedText:
    def test_includes_path_symbol_and_summary(self):
        text = CodeVectorService.build_symbol_embed_text(
            file_path="app/utils/auth/jwt_validator.py",
            symbol_kind="class",
            symbol_name="TokenAuthHelper",
            summary="功能：JWT 鉴权校验\n场景：接入用户服务鉴权时",
        )
        assert "文件: app/utils/auth/jwt_validator.py" in text
        assert "符号: class TokenAuthHelper" in text
        assert "JWT" in text or "鉴权" in text
        assert "路径词:" not in text
        assert "职责词:" not in text

    def test_empty_parts_omitted(self):
        text = CodeVectorService.build_symbol_embed_text(
            file_path="",
            symbol_kind="function",
            symbol_name="ListenAndServe",
            summary="监听并处理 HTTP 请求",
        )
        assert "文件:" not in text
        assert "符号: function ListenAndServe" in text
        assert "监听" in text
        assert "路径词:" not in text
