"""spdlog：清库重建分析。SPDLOG_CLEAR=1 python -m tests.scenarios.spdlog_oss.run_analyze"""
from __future__ import annotations
import asyncio
import os
from tests.scenarios.spdlog_oss.session_support import SpdlogOssScenarioSession


async def main() -> None:
    SpdlogOssScenarioSession.require_repo_or_skip()
    os.environ.setdefault("SPDLOG_CLEAR", "1")
    SpdlogOssScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    SpdlogOssScenarioSession._vector_ready = False
    print(
        f"[spdlog-analyze] path={SpdlogOssScenarioSession.codebase_path()} clear=1",
        flush=True,
    )
    repo_id = await SpdlogOssScenarioSession.ensure_vector_ready()
    print(f"[spdlog-analyze] done repo_id={repo_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
