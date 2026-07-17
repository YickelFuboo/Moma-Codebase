from __future__ import annotations
import os
from typing import List, Set
from app.repo_analysis.services.mr_experience.models import FileChange


class ChangeFilter:
    """规则筛选强相关变更文件：黑名单 + 改动量 Top-K。"""

    DEFAULT_TOP_K = 12
    EXCLUDED_DIR_NAMES: Set[str] = {
        "node_modules",
        "vendor",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".git",
        ".idea",
        ".vscode",
        ".pytest_cache",
        ".mypy_cache",
    }
    EXCLUDED_FILE_NAMES: Set[str] = {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "go.sum",
        "cargo.lock",
    }
    EXCLUDED_SUFFIXES = (
        ".pyc",
        ".min.js",
        ".map",
        ".lock",
    )

    @classmethod
    def select(cls, files: List[FileChange], top_k: int = DEFAULT_TOP_K) -> List[FileChange]:
        kept = [f for f in files if f.path and not cls.should_exclude(f.path)]
        kept.sort(key=lambda f: (f.churn, f.additions + f.deletions), reverse=True)
        return kept[: max(1, top_k)] if kept else []

    @classmethod
    def should_exclude(cls, path: str) -> bool:
        norm = (path or "").replace("\\", "/").strip("/")
        if not norm:
            return True
        base = os.path.basename(norm).lower()
        if base in cls.EXCLUDED_FILE_NAMES:
            return True
        lower = norm.lower()
        for suf in cls.EXCLUDED_SUFFIXES:
            if lower.endswith(suf):
                return True
        parts = lower.split("/")
        if any(p in cls.EXCLUDED_DIR_NAMES for p in parts):
            return True
        return False

    @staticmethod
    def status_action(status: str) -> str:
        st = (status or "M")[:1].upper()
        if st == "A":
            return "新增"
        if st == "D":
            return "删除"
        if st == "R":
            return "重命名/调整"
        return "修改"
