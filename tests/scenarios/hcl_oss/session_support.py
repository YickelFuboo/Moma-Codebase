from __future__ import annotations
from pathlib import Path
from tests.scenarios.oss_common.mid_oss_session import MidOssScenarioSession


class HclOssScenarioSession(MidOssScenarioSession):
    """HashiCorp HCL（Go，~190 源文件）。"""

    DEFAULT_PATH = Path(r"F:\开源项目\hcl")
    PATH_ENV = "HCL_OSS_PATH"
    CLEAR_ENV = "HCL_CLEAR"
    TAG = "hcl-oss"
    REQUIRE_MARKERS = ("hclparse", "hclsyntax", "go.mod")
    EXTRA_EXCLUDED_DIRS = MidOssScenarioSession.EXTRA_EXCLUDED_DIRS | {
        "fuzz",
        "integrationtest",
        "specsuite",
        "cmd",
        "scripts",
        ".github",
    }
    _vector_ready = False
    _session_repo_id = None
    _session_repo_path = None
