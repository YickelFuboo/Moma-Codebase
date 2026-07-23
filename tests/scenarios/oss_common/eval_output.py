"""场景评测 / 临时脚本产出目录：统一落在 tests/output。"""
from __future__ import annotations
from pathlib import Path


class ScenarioOutputDir:
    """评测 JSON/MD/日志与一次性脚本的输出根目录。"""

    _DIRNAME = "output"

    @classmethod
    def root(cls) -> Path:
        # tests/scenarios/oss_common → parents[2] = tests
        return Path(__file__).resolve().parents[2] / cls._DIRNAME

    @classmethod
    def ensure(cls) -> Path:
        path = cls.root()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def path(cls, name: str) -> Path:
        return cls.ensure() / name
