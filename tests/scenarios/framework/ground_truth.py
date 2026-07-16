"""本仓固化 ground truth（人工对照源码 import/调用关系）。"""
from __future__ import annotations
from tests.scenarios.framework.case_spec import PathSetCase, SymbolRelationCase


# ---------- 文件级依赖 ----------

FILE_DEPENDENTS_CASES = [
    PathSetCase(
        case_id="graph.dependents.gateway",
        description="谁依赖 gateway.py",
        expected_paths=[
            "app/cli/search.py",
            "app/cli/shell.py",
            "app/repo_analysis/services/analysis_service.py",
            "app/repo_analysis/services/file_analysis_service.py",
        ],
        min_precision=0.5,
        min_recall=0.75,
        extra={"file": "app/repo_analysis/services/codegraph/gateway.py"},
    ),
    PathSetCase(
        case_id="graph.dependents.base",
        description="谁依赖 codegraph/base.py",
        expected_paths=[
            "app/repo_analysis/services/codegraph/gateway.py",
            "app/repo_analysis/services/codegraph/providers/builtin/provider.py",
            "app/repo_analysis/services/codegraph/providers/codegraph/provider.py",
        ],
        min_precision=0.4,
        min_recall=0.66,
        extra={"file": "app/repo_analysis/services/codegraph/base.py"},
    ),
    PathSetCase(
        case_id="graph.dependents.search_service",
        description="谁依赖 search_service.py",
        expected_paths=[
            "app/cli/search.py",
        ],
        min_precision=0.3,
        min_recall=1.0,
        extra={"file": "app/repo_analysis/services/search_service.py"},
    ),
    PathSetCase(
        case_id="graph.dependents.providers_init",
        description="谁依赖 providers/__init__.py",
        expected_paths=[
            "app/repo_analysis/services/codegraph/gateway.py",
        ],
        min_precision=0.3,
        min_recall=1.0,
        extra={"file": "app/repo_analysis/services/codegraph/providers/__init__.py"},
    ),
]

FILE_DEPENDENCIES_CASES = [
    PathSetCase(
        case_id="graph.dependencies.gateway",
        description="gateway.py 依赖谁",
        expected_paths=[
            "app/config/settings.py",
            "app/repo_analysis/services/codegraph/base.py",
            "app/repo_analysis/services/codegraph/providers/__init__.py",
        ],
        min_precision=0.5,
        min_recall=1.0,
        extra={"file": "app/repo_analysis/services/codegraph/gateway.py"},
    ),
    PathSetCase(
        case_id="graph.dependencies.cli_search",
        description="cli/search.py 依赖谁",
        expected_paths=[
            "app/cli/common.py",
            "app/repo_analysis/services/search_service.py",
            "app/repo_analysis/services/codegraph/gateway.py",
        ],
        min_precision=0.4,
        min_recall=0.66,
        extra={"file": "app/cli/search.py"},
    ),
    PathSetCase(
        case_id="graph.dependencies.codegraph_provider",
        description="codegraph/provider.py 依赖谁",
        expected_paths=[
            "app/repo_analysis/services/codegraph/base.py",
            "app/repo_analysis/services/codegraph/model.py",
        ],
        min_precision=0.3,
        min_recall=0.5,
        extra={"file": "app/repo_analysis/services/codegraph/providers/codegraph/provider.py"},
    ),
    PathSetCase(
        case_id="graph.dependencies.analysis_service",
        description="analysis_service.py 依赖谁",
        expected_paths=[
            "app/repo_analysis/models/analysis_status.py",
            "app/repo_analysis/services/codegraph/gateway.py",
        ],
        min_precision=0.15,
        min_recall=0.5,
        extra={"file": "app/repo_analysis/services/analysis_service.py"},
    ),
]

FILE_SUMMARY_CASES = [
    PathSetCase(
        case_id="graph.summary.gateway",
        description="gateway.py 摘要应含 CodeGraphGateway",
        expected_paths=["CodeGraphGateway"],
        min_precision=0.5,
        min_recall=1.0,
        extra={"file": "app/repo_analysis/services/codegraph/gateway.py", "mode": "class_names"},
    ),
    PathSetCase(
        case_id="graph.summary.search_service",
        description="search_service.py 摘要应含 SearchService",
        expected_paths=["SearchService"],
        min_precision=0.5,
        min_recall=1.0,
        extra={"file": "app/repo_analysis/services/search_service.py", "mode": "class_names"},
    ),
]

SYMBOL_CALLERS_CASES = [
    SymbolRelationCase(
        case_id="graph.callers.create_search",
        description="谁调用 create_search",
        symbol="create_search",
        expected_paths=[
            "app/cli/search.py",
        ],
        min_precision=0.3,
        min_recall=1.0,
    ),
    SymbolRelationCase(
        case_id="graph.callers.ensure_ready",
        description="谁调用 ensure_ready",
        symbol="ensure_ready",
        expected_paths=[
            "app/cli/shell.py",
        ],
        min_precision=0.2,
        min_recall=0.5,
    ),
    SymbolRelationCase(
        case_id="graph.callers.get_provider",
        description="谁调用 get_provider",
        symbol="get_provider",
        expected_paths=[
            "app/repo_analysis/services/codegraph/gateway.py",
        ],
        min_precision=0.2,
        min_recall=0.5,
    ),
]

SYMBOL_CALLEES_CASES = [
    SymbolRelationCase(
        case_id="graph.callees.create_search",
        description="create_search 调用了谁所在文件",
        symbol="create_search",
        expected_paths=[
            "app/repo_analysis/services/codegraph/gateway.py",
        ],
        min_precision=0.2,
        min_recall=0.5,
    ),
    SymbolRelationCase(
        case_id="graph.callees.get_provider",
        description="get_provider 调用链涉及 providers",
        symbol="get_provider",
        expected_paths=[
            "app/repo_analysis/services/codegraph/providers/__init__.py",
        ],
        min_precision=0.15,
        min_recall=0.5,
    ),
]

# ---------- 向量 similar ----------

SIMILAR_CASES = [
    PathSetCase(
        case_id="vector.similar.gateway_snippet",
        description="Gateway 片段应命中 gateway.py",
        expected_paths=["app/repo_analysis/services/codegraph/gateway.py"],
        min_precision=0.2,
        min_recall=1.0,
        top_k=8,
        extra={
            "code": (
                "class CodeGraphGateway:\n"
                "    def create_search(cls):\n"
                "        return cls.get_provider().create_search()\n"
            ),
        },
    ),
    PathSetCase(
        case_id="vector.similar.cli_runner",
        description="CLI runner 片段应命中 cli_runner.py",
        expected_paths=[
            "app/repo_analysis/services/codegraph/providers/codegraph/cli_runner.py",
        ],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={
            "code": (
                "class CodeGraphCliRunner:\n"
                "    def find_cli(self):\n"
                "        return shutil.which('codegraph')\n"
            ),
        },
    ),
    PathSetCase(
        case_id="vector.similar.search_service",
        description="SearchService 片段应命中 search_service",
        expected_paths=["app/repo_analysis/services/search_service.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={
            "code": (
                "class SearchService:\n"
                "    async def search_similar_code(repo_id, code_text, top_k=10):\n"
                "        pass\n"
            ),
        },
    ),
    PathSetCase(
        case_id="vector.similar.node_parser",
        description="NodeOutputParser 片段应命中 node_parser",
        expected_paths=[
            "app/repo_analysis/services/codegraph/providers/codegraph/node_parser.py",
        ],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={
            "code": (
                "class NodeOutputParser:\n"
                "    def parse_file_relations(cls, text, self_path):\n"
                "        return dependents, dependencies\n"
            ),
        },
    ),
    PathSetCase(
        case_id="vector.similar.builtin_provider",
        description="Builtin provider 片段",
        expected_paths=[
            "app/repo_analysis/services/codegraph/providers/builtin/provider.py",
        ],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={
            "code": (
                "class BuiltinCodeGraphProvider:\n"
                "    name = 'builtin'\n"
                "    def create_search(self):\n"
                "        return _BuiltinSearch(CodeGraphSearch())\n"
            ),
        },
    ),
    PathSetCase(
        case_id="vector.similar.codegraph_model",
        description="QueryResponse model 片段",
        expected_paths=["app/repo_analysis/services/codegraph/model.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={
            "code": (
                "@dataclass\n"
                "class QueryResponse:\n"
                "    result: bool\n"
                "    content: Dict[str, Any]\n"
                "    message: str = ''\n"
            ),
        },
    ),
    PathSetCase(
        case_id="vector.similar.providers_registry",
        description="PROVIDER_REGISTRY 片段",
        expected_paths=["app/repo_analysis/services/codegraph/providers/__init__.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=8,
        extra={
            "code": (
                "PROVIDER_REGISTRY = {\n"
                "    'builtin': _builtin,\n"
                "    'codegraph': _codegraph,\n"
                "}\n"
            ),
        },
    ),
    PathSetCase(
        case_id="vector.similar.file_analysis",
        description="FileAnalysisService 片段",
        expected_paths=["app/repo_analysis/services/file_analysis_service.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={
            "code": (
                "class FileAnalysisService:\n"
                "    async def analyze_file(repo_id, file_path):\n"
                "        CodeGraphGateway.create_generator(...)\n"
            ),
        },
    ),
]

# ---------- 向量 related ----------

RELATED_CASES = [
    PathSetCase(
        case_id="vector.related.codegraph_gateway",
        description="关键词 CodeGraphGateway",
        expected_paths=["app/repo_analysis/services/codegraph/gateway.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["CodeGraphGateway", "create_search"]},
    ),
    PathSetCase(
        case_id="vector.related.search_service",
        description="关键词 SearchService",
        expected_paths=["app/repo_analysis/services/search_service.py"],
        min_precision=0.15,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["SearchService", "search_similar_code"]},
    ),
    PathSetCase(
        case_id="vector.related.cli_runner",
        description="关键词 CodeGraphCliRunner",
        expected_paths=[
            "app/repo_analysis/services/codegraph/providers/codegraph/cli_runner.py",
        ],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["CodeGraphCliRunner", "ensure_cli"]},
    ),
    PathSetCase(
        case_id="vector.related.node_parser",
        description="关键词 NodeOutputParser",
        expected_paths=[
            "app/repo_analysis/services/codegraph/providers/codegraph/node_parser.py",
        ],
        min_precision=0.05,
        min_recall=1.0,
        top_k=15,
        extra={"keywords": ["NodeOutputParser", "parse_file_relations", "_TRAIL_SECTION"]},
    ),
    PathSetCase(
        case_id="vector.related.codevector",
        description="关键词 CodeVectorService",
        expected_paths=["app/repo_analysis/services/codevector/code_vector.py"],
        min_precision=0.05,
        min_recall=1.0,
        top_k=15,
        extra={"keywords": ["CodeVectorService", "vectorize"]},
    ),
    PathSetCase(
        case_id="vector.related.analysis_service",
        description="关键词 AnalysisService",
        expected_paths=["app/repo_analysis/services/analysis_service.py"],
        min_precision=0.1,
        min_recall=1.0,
        top_k=10,
        extra={"keywords": ["AnalysisService", "start_scan"]},
    ),
]
