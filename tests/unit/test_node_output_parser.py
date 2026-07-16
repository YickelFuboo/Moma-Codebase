"""NodeOutputParser 单元测试。"""
from app.repo_analysis.services.codegraph.providers.codegraph.node_parser import NodeOutputParser


TRAIL = """
**gateway.py** (file)

**Location:** app/repo_analysis/services/codegraph/gateway.py:1
**Trail — codegraph_node any of these to follow it (no Read needed)**
**Calls →** logging (app/repo_analysis/services/codegraph/gateway.py:1), settings.py (app/config/settings.py:1), base.py (app/repo_analysis/services/codegraph/base.py:1)
**Called by ←** search.py (app/cli/search.py:1), analysis_service.py (app/repo_analysis/services/analysis_service.py:1)
"""

HEADER = """
**app/repo_analysis/services/codegraph/gateway.py** — 7 symbols, used by 3 files: app/cli/search.py, app/cli/shell.py, tests/unit/test_codegraph_gateway.py

**Symbols**
- `CodeGraphGateway` (class) — :12
- `get_provider` (method) (cls) -> CodeGraphProvider — :40
- `ensure_ready` (method) (cls) -> None — :53
"""


class TestNodeOutputParser:
    def test_parse_file_relations(self):
        deps, dcy = NodeOutputParser.parse_file_relations(
            TRAIL + "\n" + HEADER,
            "app/repo_analysis/services/codegraph/gateway.py",
        )
        assert "app/cli/search.py" in deps
        assert "app/repo_analysis/services/analysis_service.py" in deps
        assert "app/cli/shell.py" in deps
        assert "app/config/settings.py" in dcy
        assert "app/repo_analysis/services/codegraph/base.py" in dcy
        assert "app/repo_analysis/services/codegraph/gateway.py" not in dcy

    def test_parse_file_summary(self):
        summary = NodeOutputParser.parse_file_summary(
            HEADER,
            "app/repo_analysis/services/codegraph/gateway.py",
        )
        assert summary["name"] == "gateway.py"
        class_names = [c["name"] for c in summary["classes"]]
        assert "CodeGraphGateway" in class_names
        methods = summary["classes"][0]["methods"]
        method_names = [m["name"] for m in methods]
        assert "get_provider" in method_names
        assert "ensure_ready" in method_names
