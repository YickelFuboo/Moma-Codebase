"""中型开源仓串联：先分析（可清库），再跑 A–G resolve 消融。

用法（项目根）：
  poetry run python -m tests.scenarios.mid_oss.run_be_eval --only gson,express
  poetry run python -m tests.scenarios.mid_oss.run_be_eval --skip-analyze --only gson,express
  MID_OSS_CLEAR=1 poetry run python -m tests.scenarios.mid_oss.run_be_eval
"""
from __future__ import annotations
import argparse
import asyncio
import os
from tests.scenarios.express_oss.ground_truth import EXPRESS_RESOLVE_CASES
from tests.scenarios.express_oss.session_support import ExpressOssScenarioSession
from tests.scenarios.gson_oss.ground_truth import GSON_RESOLVE_CASES
from tests.scenarios.gson_oss.session_support import GsonOssScenarioSession
from tests.scenarios.hcl_oss.ground_truth import HCL_RESOLVE_CASES
from tests.scenarios.hcl_oss.session_support import HclOssScenarioSession
from tests.scenarios.nng_oss.ground_truth import NNG_RESOLVE_CASES
from tests.scenarios.nng_oss.session_support import NngOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import ALL_CONFIGS, EVAL_ORDER, run_resolve_ablation
from tests.scenarios.spdlog_oss.ground_truth import SPDLOG_RESOLVE_CASES
from tests.scenarios.spdlog_oss.session_support import SpdlogOssScenarioSession


_JOBS = (
    ("hcl", HclOssScenarioSession, HCL_RESOLVE_CASES, "HCL_CLEAR", "HCL_SKIP_REBUILD", "HCL_ABLATION_ONLY"),
    ("nng", NngOssScenarioSession, NNG_RESOLVE_CASES, "NNG_CLEAR", "NNG_SKIP_REBUILD", "NNG_ABLATION_ONLY"),
    ("spdlog", SpdlogOssScenarioSession, SPDLOG_RESOLVE_CASES, "SPDLOG_CLEAR", "SPDLOG_SKIP_REBUILD", "SPDLOG_ABLATION_ONLY"),
    ("gson", GsonOssScenarioSession, GSON_RESOLVE_CASES, "GSON_CLEAR", "GSON_SKIP_REBUILD", "GSON_ABLATION_ONLY"),
    ("express", ExpressOssScenarioSession, EXPRESS_RESOLVE_CASES, "EXPRESS_CLEAR", "EXPRESS_SKIP_REBUILD", "EXPRESS_ABLATION_ONLY"),
)


def _parse_configs(raw: str):
    text = (raw or "").strip().upper()
    if not text or text in {"ALL", "*"}:
        return list(ALL_CONFIGS)
    want = {x.strip() for x in text.replace(",", " ").split() if x.strip()}
    ordered = [c for c in ALL_CONFIGS if c.label in want]
    ordered.sort(key=lambda c: EVAL_ORDER.index(c.label) if c.label in EVAL_ORDER else 99)
    return ordered


async def _run_one(
    tag: str,
    session_cls,
    cases,
    clear_env: str,
    skip_env: str,
    only_env: str,
    *,
    do_analyze: bool,
    force_clear: bool,
    configs,
) -> None:
    labels = ",".join(c.label for c in configs)
    os.environ[only_env] = labels
    if do_analyze:
        if force_clear:
            os.environ[clear_env] = "1"
        else:
            os.environ.setdefault(clear_env, "1")
        session_cls.ENABLE_SYMBOL_SUMMARY = True
        session_cls._vector_ready = False
        await session_cls.ensure_vector_ready()
        os.environ.pop(clear_env, None)
        os.environ[skip_env] = "1"
    else:
        os.environ[skip_env] = "1"
        session_cls._vector_ready = True

    await run_resolve_ablation(
        session_cls=session_cls,
        cases=cases,
        tag=tag,
        clear_env=clear_env,
        skip_env=skip_env,
        only_env=only_env,
        configs=configs,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="中型开源仓 A–G resolve 评测")
    parser.add_argument(
        "--skip-analyze",
        action="store_true",
        help="跳过分析，直接用已有索引跑消融",
    )
    parser.add_argument(
        "--only",
        default="hcl,nng,spdlog,gson,express",
        help="逗号分隔：hcl,nng,spdlog,gson,express",
    )
    parser.add_argument(
        "--configs",
        default="A,B,C,D,E,F,G",
        help="消融档位，默认 A–G；例 B,E",
    )
    args = parser.parse_args()
    force_clear = os.environ.get("MID_OSS_CLEAR", "").strip() in {"1", "true", "True"}
    want = {x.strip().lower() for x in args.only.split(",") if x.strip()}
    configs = _parse_configs(args.configs)
    labels = ",".join(c.label for c in configs)
    for tag, session_cls, cases, clear_env, skip_env, only_env in _JOBS:
        if tag not in want:
            continue
        print(f"\n########## {tag.upper()} {labels} ##########", flush=True)
        session_cls.require_repo_or_skip()
        await _run_one(
            tag,
            session_cls,
            cases,
            clear_env,
            skip_env,
            only_env,
            do_analyze=not args.skip_analyze,
            force_clear=force_clear,
            configs=configs,
        )


if __name__ == "__main__":
    asyncio.run(main())
