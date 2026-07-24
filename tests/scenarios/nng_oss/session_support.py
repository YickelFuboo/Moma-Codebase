from __future__ import annotations
from pathlib import Path
from tests.scenarios.oss_common.mid_oss_session import MidOssScenarioSession


class NngOssScenarioSession(MidOssScenarioSession):
    """nanomsg/nng（C，~267 .c/.h）。"""

    DEFAULT_PATH = Path(r"F:\开源项目\nng")
    PATH_ENV = "NNG_OSS_PATH"
    CLEAR_ENV = "NNG_CLEAR"
    TAG = "nng-oss"
    REQUIRE_MARKERS = ("include/nng/nng.h", "src/core/socket.c")
    EXTRA_EXCLUDED_DIRS = MidOssScenarioSession.EXTRA_EXCLUDED_DIRS | {
        "tests",
        "demo",
        "cmake",
        "etc",
        ".github",
        "build",
    }
    _vector_ready = False
    _session_repo_id = None
    _session_repo_path = None
