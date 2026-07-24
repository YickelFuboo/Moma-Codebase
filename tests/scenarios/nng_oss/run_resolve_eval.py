"""nng resolve 消融。NNG_ABLATION_ONLY=B,E"""
from __future__ import annotations
import asyncio
from tests.scenarios.nng_oss.ground_truth import NNG_RESOLVE_CASES
from tests.scenarios.nng_oss.session_support import NngOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation


async def main() -> None:
    await run_resolve_ablation(
        session_cls=NngOssScenarioSession,
        cases=NNG_RESOLVE_CASES,
        tag="nng",
        clear_env="NNG_CLEAR",
        skip_env="NNG_SKIP_REBUILD",
        only_env="NNG_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
