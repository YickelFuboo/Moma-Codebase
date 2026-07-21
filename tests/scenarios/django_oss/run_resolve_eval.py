"""Django 开源仓 resolve A–F 消融。

查询时切换符号/NL2Code/rewrite；默认复用已有索引，不重建。

用法：
  DJANGO_SKIP_REBUILD=1 python -m tests.scenarios.django_oss.run_resolve_eval
  DJANGO_ABLATION_ONLY=A,D python -m tests.scenarios.django_oss.run_resolve_eval
  DJANGO_CLEAR=1 python -m tests.scenarios.django_oss.run_resolve_eval
"""
from __future__ import annotations
import asyncio
from tests.scenarios.django_oss.ground_truth import DJANGO_RESOLVE_CASES
from tests.scenarios.django_oss.session_support import DjangoOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation


async def main() -> None:
    await run_resolve_ablation(
        session_cls=DjangoOssScenarioSession,
        cases=DJANGO_RESOLVE_CASES,
        tag="django",
        clear_env="DJANGO_CLEAR",
        skip_env="DJANGO_SKIP_REBUILD",
        only_env="DJANGO_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
