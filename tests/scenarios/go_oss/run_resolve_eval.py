"""Go 开源仓 resolve A–F 消融（net/encoding/context）。

查询时切换符号/NL2Code/rewrite；默认复用已有索引，不重建。

用法：
  GO_SKIP_REBUILD=1 python -m tests.scenarios.go_oss.run_resolve_eval
  GO_ABLATION_ONLY=A,D,E,F python -m tests.scenarios.go_oss.run_resolve_eval
  GO_CLEAR=1 python -m tests.scenarios.go_oss.run_resolve_eval   # 仅当索引缺失时
"""
from __future__ import annotations
import asyncio
from tests.scenarios.go_oss.ground_truth import GO_RESOLVE_CASES
from tests.scenarios.go_oss.session_support import GoOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation


async def main() -> None:
    await run_resolve_ablation(
        session_cls=GoOssScenarioSession,
        cases=GO_RESOLVE_CASES,
        tag="go",
        clear_env="GO_CLEAR",
        skip_env="GO_SKIP_REBUILD",
        only_env="GO_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
