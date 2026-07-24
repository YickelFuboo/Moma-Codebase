"""Go + spdlog：重建符号索引后跑默认 B，对比「职责词入库」优化前后。

改前基线：排序优化后、本优化前（七仓 B 复测）。
用法：
  poetry run python -m tests.scenarios.mid_oss.run_duty_embed_b_compare
"""
from __future__ import annotations
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tests.scenarios.go_oss.ground_truth import GO_RESOLVE_CASES
from tests.scenarios.go_oss.session_support import GoOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import DEFAULT_B, run_resolve_ablation
from tests.scenarios.spdlog_oss.ground_truth import SPDLOG_RESOLVE_CASES
from tests.scenarios.spdlog_oss.session_support import SpdlogOssScenarioSession


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "tests" / "output"


@dataclass(frozen=True)
class Score:
    tag: str
    i_r: float
    u_r: float
    passed: int
    total: int


# 排序优化后、职责词入库前（_seven_repo_b_before_after.json after）
BEFORE = {
    "go": Score("go", 0.578125, 0.890625, 20, 32),
    "spdlog": Score("spdlog", 0.4479166666666667, 0.7604166666666666, 24, 32),
}

JOBS = (
    (
        "go",
        GoOssScenarioSession,
        GO_RESOLVE_CASES,
        "GO_CLEAR",
        "GO_SKIP_REBUILD",
        "GO_ABLATION_ONLY",
    ),
    (
        "spdlog",
        SpdlogOssScenarioSession,
        SPDLOG_RESOLVE_CASES,
        "SPDLOG_CLEAR",
        "SPDLOG_SKIP_REBUILD",
        "SPDLOG_ABLATION_ONLY",
    ),
)


def _score_from_rows(tag: str, rows) -> Score:
    n = len(rows)
    return Score(
        tag,
        sum(float(r.items_r) for r in rows) / n,
        sum(float(r.union_r) for r in rows) / n,
        sum(1 for r in rows if r.passed),
        n,
    )


async def _rebuild(tag: str, session_cls, clear_env: str) -> str:
    os.environ[clear_env] = "1"
    session_cls.ENABLE_SYMBOL_SUMMARY = True
    session_cls._vector_ready = False
    print(
        f"[rebuild] {tag} path={session_cls.codebase_path()} clear=1",
        flush=True,
    )
    repo_id = await session_cls.ensure_vector_ready()
    os.environ.pop(clear_env, None)
    print(f"[rebuild] {tag} done repo_id={repo_id}", flush=True)
    return str(repo_id)


async def main() -> None:
    os.environ.setdefault("RESOLVE_CHANNEL_TIMEOUT_MS", "0")
    after: dict[str, Score] = {}
    errors: list[str] = []
    for tag, session_cls, cases, clear_env, skip_env, only_env in JOBS:
        print(f"\n######## {tag}: rebuild + B ########", flush=True)
        try:
            session_cls.require_repo_or_skip()
            await _rebuild(tag, session_cls, clear_env)
            os.environ[only_env] = "B"
            os.environ[skip_env] = "1"
            session_cls._vector_ready = True
            rows = await run_resolve_ablation(
                session_cls=session_cls,
                cases=cases,
                tag=tag,
                clear_env=clear_env,
                skip_env=skip_env,
                only_env=only_env,
                configs=[DEFAULT_B],
            )
            after[tag] = _score_from_rows(tag, rows)
            s = after[tag]
            print(
                f"[after/{tag}] iR={s.i_r:.0%} uR={s.u_r:.0%} pass={s.passed}/{s.total}",
                flush=True,
            )
        except Exception as exc:
            errors.append(f"{tag}: {exc}")
            print(f"[ERROR] {tag}: {exc}", flush=True)

    lines = [
        "# Go / spdlog：职责词入库优化前后（默认 B）",
        "",
        "历史实验：路径词切分 + 职责近义词入库（已回退）；摘要 prompt 检索词提示保留。",
        "改前：排序优化后、本优化前七仓 B；改后：两仓 **CLEAR 重建索引** 后再跑 B。",
        "",
        "| 仓 | 改前 iR/uR · pass | 改后 iR/uR · pass | Δ iR | Δ uR | Δ pass |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for tag in ("go", "spdlog"):
        b = BEFORE[tag]
        a = after.get(tag)
        if a is None:
            lines.append(
                f"| {tag} | {b.i_r:.0%}/{b.u_r:.0%} · {b.passed}/{b.total} | **失败** | - | - | - |"
            )
            continue
        lines.append(
            f"| {tag} | {b.i_r:.0%}/{b.u_r:.0%} · {b.passed}/{b.total} | "
            f"**{a.i_r:.0%}/{a.u_r:.0%} · {a.passed}/{a.total}** | "
            f"{a.i_r - b.i_r:+.0%} | {a.u_r - b.u_r:+.0%} | {a.passed - b.passed:+d} |"
        )
    if errors:
        lines.extend(["", "## Errors", *[f"- {e}" for e in errors]])
    text = "\n".join(lines) + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_duty_embed_b_before_after.md").write_text(text, encoding="utf-8")
    (OUT / "_duty_embed_b_before_after.json").write_text(
        json.dumps(
            {
                "before": {k: v.__dict__ for k, v in BEFORE.items()},
                "after": {k: v.__dict__ for k, v in after.items()},
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("\n" + text, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
