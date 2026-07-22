"""Go 开源仓：三包子集清库重建分析（不跑 A–F）。

用法：
  GO_CLEAR=1 python -m tests.scenarios.go_oss.run_analyze
"""
from __future__ import annotations
import asyncio
import os
from tests.scenarios.go_oss.session_support import GoOssScenarioSession


async def main() -> None:
    GoOssScenarioSession.require_repo_or_skip()
    os.environ.setdefault("GO_CLEAR", "1")
    GoOssScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    GoOssScenarioSession._vector_ready = False
    print(
        f"[go-analyze-only] path={GoOssScenarioSession.codebase_path()} "
        f"target={GoOssScenarioSession.ANALYZE_TARGET} clear={os.environ.get('GO_CLEAR')}",
        flush=True,
    )
    repo_id = await GoOssScenarioSession.ensure_vector_ready()
    print(f"[go-analyze-only] done repo_id={repo_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
