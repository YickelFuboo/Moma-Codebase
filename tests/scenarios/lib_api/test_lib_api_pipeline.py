"""Lib 公开接口抽取与检索功能场景。"""
from __future__ import annotations
import pytest
from app.lib_analysis.services.api_extract import PublicApiExtractor
from app.lib_analysis.services.api_summary import ApiSummaryService
from app.lib_analysis.services.file_processor import LibFileProcessor
from app.lib_analysis.services.search_service import LibSearchService
from app.repo_analysis.services.codeast.ast_analyzer import FileAstAnalyzer
from tests.scenarios.lib_api.fixture_support import LibScenarioSession, MiniLibFixture


pytestmark = pytest.mark.scenario


class TestLibExtractFromMiniFixture:
    """不依赖向量库：验证迷你库公开接口抽取正确。"""

    def test_python_go_java_public_apis(self):
        fixture = MiniLibFixture()
        root = fixture.create()
        try:
            async def _collect():
                names = set()
                for rel in ("io_api.py", "hashutil.go", "JsonHelper.java"):
                    abs_path = root / rel
                    info = await FileAstAnalyzer(str(root), str(abs_path)).analyze_file()
                    source = abs_path.read_text(encoding="utf-8")
                    for api in PublicApiExtractor.extract(info, source=source):
                        names.add(api.display_name())
                return names

            names = LibScenarioSession.run_async(_collect())
            assert "read_text" in names
            assert "write_text" in names
            assert "_internal_helper" not in names
            assert "Digest" in names
            assert "hidden" not in names
            assert "JsonHelper" in names or "JsonHelper.toJson" in names
            assert "secret" not in names and "JsonHelper.secret" not in names
        finally:
            fixture.cleanup()

    def test_skips_tests_dir_file(self):
        fixture = MiniLibFixture()
        root = fixture.create()
        try:
            assert PublicApiExtractor.should_skip_file("tests/test_io.py") is True
            abs_path = root / "tests" / "test_io.py"
            info = LibScenarioSession.run_async(
                FileAstAnalyzer(str(root), str(abs_path)).analyze_file()
            )
            apis = PublicApiExtractor.extract(info, source=abs_path.read_text(encoding="utf-8"))
            assert apis == []
        finally:
            fixture.cleanup()


class TestLibAnalyzeAndSearchApi:
    """端到端：登记 lib → 分析 → search api 命中公开接口。"""

    def test_search_api_hits_read_text(self, monkeypatch):
        async def _fixed_summary(api):
            return (
                f"功能：{api.docstring or api.display_name()} 相关能力\n"
                f"关键参数：{api.signature}\n"
                f"返回：公开接口"
            )

        monkeypatch.setattr(ApiSummaryService, "summarize", staticmethod(_fixed_summary))

        fixture = MiniLibFixture()
        root = fixture.create()

        async def _pipeline():
            repo_id = await LibScenarioSession.register_lib(root)
            # 直接处理源文件，避免调度竞态；再验证 search
            for rel in ("io_api.py", "hashutil.go", "JsonHelper.java"):
                abs_path = root / rel
                ok, err = await LibFileProcessor.analyze_file(
                    repo_id=repo_id,
                    repo_path=str(root),
                    rel_file_path=rel,
                    abs_file_path=str(abs_path),
                )
                assert ok, err

            result = await LibSearchService.search_apis(
                repo_id=repo_id,
                query="读取文本文件内容",
                top_k=5,
            )
            return result

        try:
            result = LibScenarioSession.run_async(_pipeline())
            assert result["total"] > 0
            names = {item.get("api_name") for item in result["items"]}
            assert "read_text" in names or any(
                "read_text" in str(item.get("summary") or "") for item in result["items"]
            )
            # 至少返回结构化字段
            first = result["items"][0]
            assert first.get("file_path")
            assert first.get("api_name")
            assert first.get("summary")
        except Exception as exc:
            msg = str(exc).lower()
            if "embedding" in msg or "模型" in msg or "vector" in msg:
                pytest.skip(f"环境缺少可用 embedding，跳过检索场景: {exc}")
            raise
        finally:
            try:
                LibScenarioSession.run_async(LibScenarioSession.shutdown())
            except Exception:
                pass
            fixture.cleanup()

    def test_search_api_rejects_before_analyze(self):
        fixture = MiniLibFixture()
        root = fixture.create()

        async def _run():
            repo_id = await LibScenarioSession.register_lib(root)
            with pytest.raises(ValueError, match="尚未完成分析"):
                await LibSearchService.search_apis(repo_id, "任意查询")

        try:
            LibScenarioSession.run_async(_run())
        except Exception as exc:
            msg = str(exc).lower()
            if "embedding" in msg or "模型" in msg:
                pytest.skip(f"环境缺少可用 embedding: {exc}")
            raise
        finally:
            try:
                LibScenarioSession.run_async(LibScenarioSession.shutdown())
            except Exception:
                pass
            fixture.cleanup()
