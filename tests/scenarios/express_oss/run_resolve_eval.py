"""Express resolve 消融。EXPRESS_ABLATION_ONLY=ALL"""
from __future__ import annotations
import asyncio
from tests.scenarios.express_oss.ground_truth import EXPRESS_RESOLVE_CASES
from tests.scenarios.express_oss.session_support import ExpressOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation


async def main() -> None:
    await run_resolve_ablation(
        session_cls=ExpressOssScenarioSession,
        cases=EXPRESS_RESOLVE_CASES,
        tag="express",
        clear_env="EXPRESS_CLEAR",
        skip_env="EXPRESS_SKIP_REBUILD",
        only_env="EXPRESS_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
