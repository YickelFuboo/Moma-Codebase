import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from app.lib_analysis.services.file_processor import LibFileProcessor


class TestLibFileProcessor:
    def test_skip_test_file(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "test_foo.py"
        f.write_text("def foo():\n    pass\n", encoding="utf-8")
        deleted = AsyncMock(return_value=0)
        monkeypatch.setattr(
            "app.lib_analysis.services.file_processor.ApiVectorService.delete_file_vector_records",
            deleted,
        )

        async def _run():
            return await LibFileProcessor.analyze_file(
                repo_id="r1",
                repo_path=str(tmp_path),
                rel_file_path="test_foo.py",
                abs_file_path=str(f),
            )

        ok, err = asyncio.run(_run())
        assert ok is True
        assert err is None
        deleted.assert_awaited()

    def test_skip_unsupported_extension(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "x.cpp"
        f.write_text("int main(){return 0;}", encoding="utf-8")
        deleted = AsyncMock(return_value=0)
        monkeypatch.setattr(
            "app.lib_analysis.services.file_processor.ApiVectorService.delete_file_vector_records",
            deleted,
        )

        async def _run():
            return await LibFileProcessor.analyze_file(
                repo_id="r1",
                repo_path=str(tmp_path),
                rel_file_path="x.cpp",
                abs_file_path=str(f),
            )

        ok, err = asyncio.run(_run())
        assert ok is True
        assert err is None
        deleted.assert_awaited()

    def test_analyze_python_public_api(self, tmp_path: Path, monkeypatch):
        f = tmp_path / "io_api.py"
        f.write_text(
            '"""io helpers"""\n'
            "def read_text(path: str) -> str:\n"
            '    """读取文本文件"""\n'
            "    return open(path, encoding='utf-8').read()\n"
            "\n"
            "def _secret():\n"
            "    return 1\n",
            encoding="utf-8",
        )
        stored = AsyncMock()
        monkeypatch.setattr(
            "app.lib_analysis.services.file_processor.ApiVectorService.vectorize_and_store_apis",
            stored,
        )

        async def _run():
            return await LibFileProcessor.analyze_file(
                repo_id="r1",
                repo_path=str(tmp_path),
                rel_file_path="io_api.py",
                abs_file_path=str(f),
            )

        ok, err = asyncio.run(_run())
        assert ok is True, err
        assert err is None
        stored.assert_awaited()
        args = stored.await_args.args
        assert args[0] == "r1"
        assert args[1] == "io_api.py"
        apis = args[2]
        names = {a.display_name() for a in apis}
        assert "read_text" in names
        assert "_secret" not in names
