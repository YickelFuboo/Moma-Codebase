from __future__ import annotations
from pathlib import Path
from tests.scenarios.oss_common.mid_oss_session import MidOssScenarioSession


class SpdlogOssScenarioSession(MidOssScenarioSession):
    """gabime/spdlog（C++，~150 源文件）。"""

    DEFAULT_PATH = Path(r"F:\开源项目\spdlog")
    PATH_ENV = "SPDLOG_OSS_PATH"
    CLEAR_ENV = "SPDLOG_CLEAR"
    TAG = "spdlog-oss"
    REQUIRE_MARKERS = ("include/spdlog/spdlog.h", "include/spdlog/logger.h")
    EXTRA_EXCLUDED_DIRS = MidOssScenarioSession.EXTRA_EXCLUDED_DIRS | {
        "tests",
        "bench",
        "example",
        "cmake",
        "scripts",
        "logos",
        ".github",
        "build",
    }
    _vector_ready = False
    _session_repo_id = None
    _session_repo_path = None
