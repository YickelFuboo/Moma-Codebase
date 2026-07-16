from app.lib_analysis.schemes.public_api import PublicApi
from app.lib_analysis.services.api_extract.public_api_extractor import PublicApiExtractor
from app.repo_analysis.services.codeast.model import (
    ClassInfo,
    ClassType,
    FileInfo,
    FunctionInfo,
    FunctionType,
    Language,
)


def _fn(
    name: str,
    *,
    signature: str = "",
    source: str = "",
    start: int = 1,
    end: int = 2,
    docstring: str = None,
) -> FunctionInfo:
    return FunctionInfo(
        name=name,
        full_name=name,
        signature=signature or f"{name}()",
        type=FunctionType.FUNCTION.value,
        source_code=source or f"def {name}():\n    pass",
        params=[],
        param_types=[],
        returns=[],
        return_types=[],
        file_path="mod.py",
        start_line=start,
        end_line=end,
        docstring=docstring,
    )


class TestPublicApiExtractorSkipFile:
    def test_skip_tests_dir(self):
        assert PublicApiExtractor.should_skip_file("pkg/tests/test_x.py") is True

    def test_skip_go_test(self):
        assert PublicApiExtractor.should_skip_file("pkg/foo_test.go") is True

    def test_skip_java_test_name(self):
        assert PublicApiExtractor.should_skip_file("FooTest.java") is True

    def test_keep_normal(self):
        assert PublicApiExtractor.should_skip_file("pkg/api.py") is False

    def test_extract_none_file_info(self):
        assert PublicApiExtractor.extract(None) == []

    def test_extract_unknown_language(self):
        info = FileInfo(
            name="a.js",
            file_path="a.js",
            language="javascript",
            functions=[_fn("foo")],
            classes=[],
            imports=[],
        )
        assert PublicApiExtractor.extract(info) == []


class TestPublicApiExtractorPython:
    def test_filters_private_and_respects_all(self):
        source = '__all__ = ["public_fn"]\n'
        file_info = FileInfo(
            name="mod.py",
            file_path="mod.py",
            language=Language.PYTHON.value,
            functions=[
                _fn("public_fn"),
                _fn("_hidden"),
                _fn("other_public"),
            ],
            classes=[],
            imports=[],
        )
        apis = PublicApiExtractor.extract(file_info, source=source)
        names = {a.display_name() for a in apis}
        assert names == {"public_fn"}

    def test_without_all_skips_underscore(self):
        file_info = FileInfo(
            name="mod.py",
            file_path="mod.py",
            language=Language.PYTHON.value,
            functions=[_fn("ok"), _fn("_no")],
            classes=[
                ClassInfo(
                    name="Svc",
                    full_name="Svc",
                    file_path="mod.py",
                    node_type=ClassType.CLASS.value,
                    source_code="class Svc:\n    pass",
                    start_line=1,
                    end_line=2,
                    methods=[
                        _fn("run", source="def run(self):\n    return 1"),
                        _fn("_priv", source="def _priv(self):\n    return 0"),
                        _fn("__init__", source="def __init__(self):\n    pass"),
                    ],
                )
            ],
            imports=[],
        )
        apis = PublicApiExtractor.extract(file_info, source="")
        names = {a.display_name() for a in apis}
        assert "ok" in names
        assert "Svc" in names
        assert "Svc.run" in names
        assert "_no" not in names
        assert "Svc._priv" not in names
        assert "Svc.__init__" not in names

    def test_skips_when_path_is_test(self):
        file_info = FileInfo(
            name="test_x.py",
            file_path="pkg/test_x.py",
            language=Language.PYTHON.value,
            functions=[_fn("ok")],
            classes=[],
            imports=[],
        )
        assert PublicApiExtractor.extract(file_info) == []


class TestPublicApiExtractorGo:
    def test_exported_only(self):
        file_info = FileInfo(
            name="api.go",
            file_path="api.go",
            language=Language.GO.value,
            functions=[
                FunctionInfo(
                    name="Open",
                    full_name="Open",
                    signature="Open()",
                    type=FunctionType.FUNCTION.value,
                    source_code="func Open() {}",
                    params=[],
                    param_types=[],
                    returns=[],
                    return_types=[],
                    file_path="api.go",
                    start_line=1,
                    end_line=1,
                ),
                FunctionInfo(
                    name="hidden",
                    full_name="hidden",
                    signature="hidden()",
                    type=FunctionType.FUNCTION.value,
                    source_code="func hidden() {}",
                    params=[],
                    param_types=[],
                    returns=[],
                    return_types=[],
                    file_path="api.go",
                    start_line=2,
                    end_line=2,
                ),
            ],
            classes=[],
            imports=[],
        )
        apis = PublicApiExtractor.extract(file_info)
        assert [a.name for a in apis] == ["Open"]


class TestPublicApiExtractorJava:
    def test_public_only(self):
        file_info = FileInfo(
            name="Api.java",
            file_path="Api.java",
            language=Language.JAVA.value,
            functions=[],
            classes=[
                ClassInfo(
                    name="Api",
                    full_name="com.x.Api",
                    file_path="Api.java",
                    node_type=ClassType.CLASS.value,
                    source_code="public class Api {\n}",
                    start_line=1,
                    end_line=10,
                    methods=[
                        FunctionInfo(
                            name="call",
                            full_name="com.x.Api.call",
                            signature="call() -> void",
                            type=FunctionType.METHOD.value,
                            source_code="public void call() {}",
                            params=[],
                            param_types=[],
                            returns=["void"],
                            return_types=["void"],
                            file_path="Api.java",
                            start_line=3,
                            end_line=4,
                        ),
                        FunctionInfo(
                            name="hide",
                            full_name="com.x.Api.hide",
                            signature="hide() -> void",
                            type=FunctionType.METHOD.value,
                            source_code="private void hide() {}",
                            params=[],
                            param_types=[],
                            returns=["void"],
                            return_types=["void"],
                            file_path="Api.java",
                            start_line=5,
                            end_line=6,
                        ),
                    ],
                )
            ],
            imports=[],
        )
        apis = PublicApiExtractor.extract(file_info)
        names = {a.display_name() for a in apis}
        assert "Api" in names
        assert "Api.call" in names
        assert "Api.hide" not in names


class TestPublicApiDisplayName:
    def test_method_display(self):
        api = PublicApi(
            name="run",
            kind="method",
            signature="run()",
            file_path="a.py",
            language="python",
            start_line=1,
            end_line=2,
            class_name="Svc",
        )
        assert api.display_name() == "Svc.run"
