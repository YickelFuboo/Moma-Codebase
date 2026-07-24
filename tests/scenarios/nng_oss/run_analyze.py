"""nng：清库重建分析。NNG_CLEAR=1 python -m tests.scenarios.nng_oss.run_analyze"""
from __future__ import annotations
import asyncio
import os
from tests.scenarios.nng_oss.session_support import NngOssScenarioSession


async def main() -> None:
    NngOssScenarioSession.require_repo_or_skip()
    os.environ.setdefault("NNG_CLEAR", "1")
    NngOssScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    NngOssScenarioSession._vector_ready = False
    print(f"[nng-analyze] path={NngOssScenarioSession.codebase_path()} clear=1", flush=True)
    repo_id = await NngOssScenarioSession.ensure_vector_ready()
    print(f"[nng-analyze] done repo_id={repo_id}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
