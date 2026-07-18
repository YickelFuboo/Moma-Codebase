from types import SimpleNamespace
from app.config.settings import settings
from app.repo_analysis.services.codechunk.code_chunk import CodeChunkService


def _fn(name: str, start: int, end: int, body: str):
    return SimpleNamespace(
        name=name,
        start_line=start,
        end_line=end,
        source_code=body,
    )


def _file_info(*, functions=None, classes=None):
    return SimpleNamespace(functions=functions or [], classes=classes or [])


class TestSliceSymbolBodiesLimits:
    def test_skip_oversized_class_keep_methods(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_symbol_body_max_lines_class", 120)
        monkeypatch.setattr(settings, "code_analysis_symbol_body_max_lines_function", 500)
        big_class_body = "\n".join([f"    def m{i}(self): return {i}" for i in range(200)])
        class_src = f"class Big:\n{big_class_body}\n"
        method_body = "def ok(self):\n    return 1\n    # pad\n" + ("    x = 1\n" * 20)
        info = _file_info(
            classes=[
                SimpleNamespace(
                    name="Big",
                    start_line=1,
                    end_line=220,
                    source_code=class_src,
                    methods=[
                        _fn("ok", 2, 24, method_body),
                        _fn("huge", 25, 600, "def huge(self):\n" + ("    pass\n" * 580)),
                    ],
                )
            ]
        )
        chunks = CodeChunkService.slice_symbol_bodies(info, file_ext=".py")
        spans = {(c.start_line, c.end_line) for c in chunks}
        assert (1, 220) not in spans
        assert (2, 24) in spans
        assert (25, 600) not in spans

    def test_keep_small_class(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_symbol_body_max_lines_class", 120)
        method_body = (
            "def a(self):\n"
            "    total = 0\n"
            "    for i in range(10):\n"
            "        total += i\n"
            "    return total\n"
        )
        body = "class Tiny:\n" + "\n".join("    " + ln for ln in method_body.splitlines()) + "\n"
        info = _file_info(
            classes=[
                SimpleNamespace(
                    name="Tiny",
                    start_line=1,
                    end_line=6,
                    source_code=body,
                    methods=[_fn("a", 2, 6, method_body)],
                )
            ]
        )
        chunks = CodeChunkService.slice_symbol_bodies(info, file_ext=".py")
        spans = {(c.start_line, c.end_line) for c in chunks}
        assert (1, 6) in spans
        assert (2, 6) in spans

    def test_keep_function_within_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "code_analysis_symbol_body_max_lines_function", 500)
        body = "def foo():\n" + ("    x = 1\n" * 40)
        info = _file_info(functions=[_fn("foo", 1, 41, body)])
        chunks = CodeChunkService.slice_symbol_bodies(info, file_ext=".py")
        assert len(chunks) == 1
        assert chunks[0].start_line == 1 and chunks[0].end_line == 41
