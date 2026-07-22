"""KnowledegBase-Service：resolve A–F 消融评测。

用法：
  KB_SKIP_REBUILD=1 KB_ABLATION_ONLY=ALL python -m tests.scenarios.knowledge_base.run_resolve_eval
  KB_CLEAR=1 python -m tests.scenarios.knowledge_base.run_resolve_eval
"""
from __future__ import annotations
import asyncio
from tests.scenarios.knowledge_base.ground_truth import KB_RESOLVE_CASES
from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession
from tests.scenarios.oss_common.resolve_eval import run_resolve_ablation


async def main() -> None:
    await run_resolve_ablation(
        session_cls=KnowledgeBaseScenarioSession,
        cases=KB_RESOLVE_CASES,
        tag="kb",
        clear_env="KB_CLEAR",
        skip_env="KB_SKIP_REBUILD",
        only_env="KB_ABLATION_ONLY",
    )


if __name__ == "__main__":
    asyncio.run(main())
