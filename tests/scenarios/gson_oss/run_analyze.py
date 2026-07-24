"""Gson：清库重建分析。GSON_CLEAR=1 python -m tests.scenarios.gson_oss.run_analyze"""
from __future__ import annotations
import asyncio
import os
from tests.scenarios.gson_oss.session_support import GsonOssScenarioSession


async def main() -> None:
    GsonOssScenarioSession.require_repo_or_skip()
    os.environ.setdefault("GSON_CLEAR", "1")
    GsonOssScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    GsonOssScenarioSession._vector_ready = False
    print(
        f"[gson-analyze] path={GsonOssScenarioSession.codebase_path()} "
        f"target={GsonOssScenarioSession.ANALYZE_TARGET} clear=1",
        flush=True,
    )
    repo_id = await GsonOssScenarioSession.ensure_vector_ready()
    print(f"[gson-analyze] done repo_id={repo_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
