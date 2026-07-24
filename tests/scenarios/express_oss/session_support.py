from __future__ import annotations
from pathlib import Path
from tests.scenarios.oss_common.mid_oss_session import MidOssScenarioSession


class ExpressOssScenarioSession(MidOssScenarioSession):
    """expressjs/express（JavaScript，lib 核心）。"""

    DEFAULT_PATH = Path(r"F:\开源项目\express")
    PATH_ENV = "EXPRESS_OSS_PATH"
    CLEAR_ENV = "EXPRESS_CLEAR"
    TAG = "express-oss"
    REQUIRE_MARKERS = ("lib/application.js", "package.json")
    EXTRA_EXCLUDED_DIRS = MidOssScenarioSession.EXTRA_EXCLUDED_DIRS | {
        "test",
        "tests",
        "examples",
        "example",
        "benchmarks",
        "benchmark",
        "coverage",
        ".github",
        "docs",
        "node_modules",
    }
    _vector_ready = False
    _session_repo_id = None
    _session_repo_path = None
