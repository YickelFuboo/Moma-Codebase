"""spdlog resolve 消融。SPDLOG_ABLATION_ONLY=B,E"""
from __future__ import annotations
import asyncio
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation
from tests.scenarios.spdlog_oss.ground_truth import SPDLOG_RESOLVE_CASES
from tests.scenarios.spdlog_oss.session_support import SpdlogOssScenarioSession


async def main() -> None:
    await run_resolve_ablation(
        session_cls=SpdlogOssScenarioSession,
        cases=SPDLOG_RESOLVE_CASES,
        tag="spdlog",
        clear_env="SPDLOG_CLEAR",
        skip_env="SPDLOG_SKIP_REBUILD",
        only_env="SPDLOG_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
