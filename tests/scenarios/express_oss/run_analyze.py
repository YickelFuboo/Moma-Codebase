"""Express：清库重建分析。EXPRESS_CLEAR=1 python -m tests.scenarios.express_oss.run_analyze"""
from __future__ import annotations
import asyncio
import os
from tests.scenarios.express_oss.session_support import ExpressOssScenarioSession


async def main() -> None:
    ExpressOssScenarioSession.require_repo_or_skip()
    os.environ.setdefault("EXPRESS_CLEAR", "1")
    ExpressOssScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    ExpressOssScenarioSession._vector_ready = False
    print(
        f"[express-analyze] path={ExpressOssScenarioSession.codebase_path()} clear=1",
        flush=True,
    )
    repo_id = await ExpressOssScenarioSession.ensure_vector_ready()
    print(f"[express-analyze] done repo_id={repo_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
