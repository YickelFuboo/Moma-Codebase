import asyncio
from pathlib import Path
from app.repo_analysis.services.codeast.ast_analyzer import FileAstAnalyzer
from app.repo_analysis.services.codeast.model import Language


class TestTsRustAnalyzers:
    def test_typescript_functions_and_classes(self, tmp_path: Path):
        f = tmp_path / "svc.ts"
        f.write_text(
            "export function ping(): string { return 'pong'; }\n"
            "export class Client {\n"
            "  connect(): void {}\n"
            "}\n",
            encoding="utf-8",
        )

        async def _run():
            return await FileAstAnalyzer(str(tmp_path), str(f)).analyze_file()

        info = asyncio.run(_run())
        assert info is not None
        assert info.language == Language.TYPESCRIPT
        assert {fn.name for fn in info.functions} == {"ping"}
        assert {cl.name for cl in info.classes} == {"Client"}
        assert {m.name for m in info.classes[0].methods} == {"connect"}

    def test_rust_pub_and_impl(self, tmp_path: Path):
        f = tmp_path / "lib.rs"
        f.write_text(
            "pub fn open() {}\n"
            "fn hidden() {}\n"
            "pub struct Store {}\n"
            "impl Store {\n"
            "  pub fn load(&self) {}\n"
            "}\n",
            encoding="utf-8",
        )

        async def _run():
            return await FileAstAnalyzer(str(tmp_path), str(f)).analyze_file()

        info = asyncio.run(_run())
        assert info is not None
        assert info.language == Language.RUST
        names = {fn.name for fn in info.functions}
        assert "open" in names
        assert "hidden" in names
        assert any(cl.name == "Store" for cl in info.classes)
        impl = next(cl for cl in info.classes if cl.methods)
        assert {m.name for m in impl.methods} == {"load"}

    def test_javascript_export_declaration(self, tmp_path: Path):
        f = tmp_path / "mod.js"
        f.write_text(
            "export function add(a, b) { return a + b; }\n"
            "function privateHelper() { return 0; }\n",
            encoding="utf-8",
        )

        async def _run():
            return await FileAstAnalyzer(str(tmp_path), str(f)).analyze_file()

        info = asyncio.run(_run())
        assert info is not None
        assert info.language == Language.JAVASCRIPT
        assert {fn.name for fn in info.functions} == {"add", "privateHelper"}
