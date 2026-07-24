"""HCL resolve 消融。默认复用索引；HCL_CLEAR=1 重建；HCL_ABLATION_ONLY=B,E 只跑指定档。"""
from __future__ import annotations
import asyncio
from tests.scenarios.hcl_oss.ground_truth import HCL_RESOLVE_CASES
from tests.scenarios.hcl_oss.session_support import HclOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation


async def main() -> None:
    await run_resolve_ablation(
        session_cls=HclOssScenarioSession,
        cases=HCL_RESOLVE_CASES,
        tag="hcl",
        clear_env="HCL_CLEAR",
        skip_env="HCL_SKIP_REBUILD",
        only_env="HCL_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
