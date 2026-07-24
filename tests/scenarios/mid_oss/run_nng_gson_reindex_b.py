"""NNG + Gson：重建索引后跑默认 B（历史对比脚本；路径词入库已回退）。

改前基线：排序优化后、重建前（七仓 B 复测 after）。
用法：
  poetry run python -m tests.scenarios.mid_oss.run_nng_gson_reindex_b
"""
from __future__ import annotations
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tests.scenarios.gson_oss.ground_truth import GSON_RESOLVE_CASES
from tests.scenarios.gson_oss.session_support import GsonOssScenarioSession
from tests.scenarios.nng_oss.ground_truth import NNG_RESOLVE_CASES
from tests.scenarios.nng_oss.session_support import NngOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import DEFAULT_B, run_resolve_ablation


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "tests" / "output"


@dataclass(frozen=True)
class Score:
    tag: str
    i_r: float
    u_r: float
    passed: int
    total: int


# 排序优化后、路径词入库/中立摘要前（_seven_repo_b_before_after.json after）
BEFORE = {
    "nng": Score("nng", 0.5416666666666666, 0.7968749999999999, 25, 32),
    "gson": Score("gson", 0.8177083333333334, 0.953125, 28, 32),
}

# Gson 先（小仓、易验调度）；NNG 后（避免大仓超时拖死后续）
JOBS = (
    ("gson", GsonOssScenarioSession, GSON_RESOLVE_CASES, "GSON_CLEAR", "GSON_SKIP_REBUILD", "GSON_ABLATION_ONLY"),
    ("nng", NngOssScenarioSession, NNG_RESOLVE_CASES, "NNG_CLEAR", "NNG_SKIP_REBUILD", "NNG_ABLATION_ONLY"),
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
    from app.repo_analysis.services.file_analysis_service import FileAnalysisService

    os.environ[clear_env] = "1"
    session_cls.ENABLE_SYMBOL_SUMMARY = True
    session_cls._vector_ready = False
    await FileAnalysisService.stop_global_scheduler()
    for other_id in list(FileAnalysisService._running_tasks.keys()):
        try:
            await FileAnalysisService.stop_analysis(other_id)
        except Exception:
            pass
    print(f"[rebuild] {tag} path={session_cls.codebase_path()} clear=1", flush=True)
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
        "# NNG / Gson：重建索引后默认 B 对比",
        "",
        "改动曾含路径词切分入库（已回退）、摘要领域中立、检索排序。",
        "改前：七仓 B 排序优化后数字（未重建）；改后：两仓 CLEAR 重建后再跑 B。",
        "",
        "| 仓 | 改前 iR/uR · pass | 改后 iR/uR · pass | Δ iR | Δ uR | Δ pass |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for tag in ("nng", "gson"):
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
    (OUT / "_nng_gson_reindex_b.md").write_text(text, encoding="utf-8")
    (OUT / "_nng_gson_reindex_b.json").write_text(
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
    print(f"[write] {OUT / '_nng_gson_reindex_b.md'}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
