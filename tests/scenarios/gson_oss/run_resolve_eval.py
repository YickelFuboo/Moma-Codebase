"""Gson resolve 消融。GSON_ABLATION_ONLY=ALL"""
from __future__ import annotations
import asyncio
from tests.scenarios.gson_oss.ground_truth import GSON_RESOLVE_CASES
from tests.scenarios.gson_oss.session_support import GsonOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation


async def main() -> None:
    await run_resolve_ablation(
        session_cls=GsonOssScenarioSession,
        cases=GSON_RESOLVE_CASES,
        tag="gson",
        clear_env="GSON_CLEAR",
        skip_env="GSON_SKIP_REBUILD",
        only_env="GSON_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
