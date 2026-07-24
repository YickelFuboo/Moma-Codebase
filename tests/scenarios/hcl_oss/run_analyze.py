"""HCL：清库重建分析。

用法：HCL_CLEAR=1 python -m tests.scenarios.hcl_oss.run_analyze
"""
from __future__ import annotations
import asyncio
import os
from tests.scenarios.hcl_oss.session_support import HclOssScenarioSession


async def main() -> None:
    HclOssScenarioSession.require_repo_or_skip()
    os.environ.setdefault("HCL_CLEAR", "1")
    HclOssScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    HclOssScenarioSession._vector_ready = False
    print(
        f"[hcl-analyze] path={HclOssScenarioSession.codebase_path()} clear=1",
        flush=True,
    )
    repo_id = await HclOssScenarioSession.ensure_vector_ready()
    print(f"[hcl-analyze] done repo_id={repo_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
