from __future__ import annotations
from pathlib import Path
from tests.scenarios.oss_common.mid_oss_session import MidOssScenarioSession


class GsonOssScenarioSession(MidOssScenarioSession):
    """google/gson（Java，主模块 ~120 源文件）。"""

    DEFAULT_PATH = Path(r"F:\开源项目\gson")
    PATH_ENV = "GSON_OSS_PATH"
    CLEAR_ENV = "GSON_CLEAR"
    TAG = "gson-oss"
    ANALYZE_TARGET = "gson/src/main/java"
    REQUIRE_MARKERS = ("gson/src/main/java/com/google/gson/Gson.java",)
    EXTRA_EXCLUDED_DIRS = MidOssScenarioSession.EXTRA_EXCLUDED_DIRS | {
        "test",
        "androidTest",
        "examples",
        "metrics",
        "proto",
        ".github",
        "build",
        "out",
        "target",
        "graal-native-image-test",
        "codegen",
    }
    _vector_ready = False
    _session_repo_id = None
    _session_repo_path = None
