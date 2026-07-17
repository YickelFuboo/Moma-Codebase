"""符号向量入库文本 UT。"""
from app.repo_analysis.services.codevector.code_vector import CodeVectorService


class TestSymbolEmbedText:
    def test_includes_path_and_business_summary(self):
        text = CodeVectorService.build_symbol_embed_text(
            file_path="app/utils/auth/jwt_validator.py",
            symbol_kind="class",
            symbol_name="TokenAuthHelper",
            summary="功能：JWT 鉴权校验\n场景：接入用户服务鉴权时",
        )
        assert "jwt_validator" in text
        assert "TokenAuthHelper" in text
        assert "JWT" in text or "鉴权" in text
        assert "文件:" in text
