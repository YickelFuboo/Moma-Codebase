from app.lib_analysis.constants import LibAnalysisType, api_summary_space_name
from app.lib_analysis.schemes.public_api import PublicApi
from app.lib_analysis.services.api_summary import ApiSummaryService


class TestApiSummarySpace:
    def test_space_name(self):
        assert api_summary_space_name("abc", 384) == "lib_abc_api_summary_384"

    def test_analysis_type(self):
        assert LibAnalysisType.API_SUMMARY_VECTOR == "api_summary_vector"


class TestApiSummaryFallback:
    def test_fallback_with_docstring(self):
        api = PublicApi(
            name="open_file",
            kind="function",
            signature="open_file(path: str) -> str",
            file_path="io_api.py",
            language="python",
            start_line=1,
            end_line=5,
            docstring="打开并读取文本文件内容",
            return_types=["str"],
        )
        text = ApiSummaryService.fallback_summary(api)
        assert "打开并读取文本文件内容" in text
        assert "open_file(path: str) -> str" in text

    def test_fallback_without_docstring(self):
        api = PublicApi(
            name="Ping",
            kind="function",
            signature="Ping()",
            file_path="a.go",
            language="go",
            start_line=1,
            end_line=1,
        )
        text = ApiSummaryService.fallback_summary(api)
        assert "Ping" in text
        assert "摘要回退" in text

    def test_build_llm_input_contains_core_fields(self):
        api = PublicApi(
            name="call",
            kind="method",
            signature="call(x: int) -> void",
            file_path="Api.java",
            language="java",
            start_line=3,
            end_line=4,
            params=["x"],
            param_types=["int"],
            return_types=["void"],
            class_name="Api",
            source_code="public void call(int x) {}",
        )
        content = ApiSummaryService._build_llm_input(api)
        assert "Api.call" in content
        assert "java" in content
        assert "int" in content
