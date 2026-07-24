"""七仓默认 B 重跑（skip rebuild），并与优化前 Design 基线对比。

用法（项目根）：
  poetry run python -m tests.scenarios.mid_oss.run_b_before_after
"""
from __future__ import annotations
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from tests.scenarios.django_oss.ground_truth import DJANGO_RESOLVE_CASES
from tests.scenarios.django_oss.session_support import DjangoOssScenarioSession
from tests.scenarios.express_oss.ground_truth import EXPRESS_RESOLVE_CASES
from tests.scenarios.express_oss.session_support import ExpressOssScenarioSession
from tests.scenarios.go_oss.ground_truth import GO_RESOLVE_CASES
from tests.scenarios.go_oss.session_support import GoOssScenarioSession
from tests.scenarios.gson_oss.ground_truth import GSON_RESOLVE_CASES
from tests.scenarios.gson_oss.session_support import GsonOssScenarioSession
from tests.scenarios.hcl_oss.ground_truth import HCL_RESOLVE_CASES
from tests.scenarios.hcl_oss.session_support import HclOssScenarioSession
from tests.scenarios.nng_oss.ground_truth import NNG_RESOLVE_CASES
from tests.scenarios.nng_oss.session_support import NngOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import DEFAULT_B, run_resolve_ablation
from tests.scenarios.spdlog_oss.ground_truth import SPDLOG_RESOLVE_CASES
from tests.scenarios.spdlog_oss.session_support import SpdlogOssScenarioSession


ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "tests" / "output"


@dataclass(frozen=True)
class Baseline:
    tag: str
    i_r: float
    u_r: float
    passed: int
    total: int


# Design.md §5.12 排序优化前 B 基线
BEFORE: List[Baseline] = [
    Baseline("go", 0.58, 0.89, 20, 32),
    Baseline("django", 0.85, 0.98, 28, 33),
    Baseline("hcl", 0.58, 0.77, 21, 32),
    Baseline("nng", 0.55, 0.80, 24, 32),
    Baseline("spdlog", 0.41, 0.71, 18, 32),
    Baseline("gson", 0.72, 0.90, 24, 32),
    Baseline("express", 0.64, 1.00, 21, 32),
]

JOBS = (
    ("go", GoOssScenarioSession, GO_RESOLVE_CASES, "GO_CLEAR", "GO_SKIP_REBUILD", "GO_ABLATION_ONLY"),
    (
        "django",
        DjangoOssScenarioSession,
        DJANGO_RESOLVE_CASES,
        "DJANGO_CLEAR",
        "DJANGO_SKIP_REBUILD",
        "DJANGO_ABLATION_ONLY",
    ),
    ("hcl", HclOssScenarioSession, HCL_RESOLVE_CASES, "HCL_CLEAR", "HCL_SKIP_REBUILD", "HCL_ABLATION_ONLY"),
    ("nng", NngOssScenarioSession, NNG_RESOLVE_CASES, "NNG_CLEAR", "NNG_SKIP_REBUILD", "NNG_ABLATION_ONLY"),
    (
        "spdlog",
        SpdlogOssScenarioSession,
        SPDLOG_RESOLVE_CASES,
        "SPDLOG_CLEAR",
        "SPDLOG_SKIP_REBUILD",
        "SPDLOG_ABLATION_ONLY",
    ),
    ("gson", GsonOssScenarioSession, GSON_RESOLVE_CASES, "GSON_CLEAR", "GSON_SKIP_REBUILD", "GSON_ABLATION_ONLY"),
    (
        "express",
        ExpressOssScenarioSession,
        EXPRESS_RESOLVE_CASES,
        "EXPRESS_CLEAR",
        "EXPRESS_SKIP_REBUILD",
        "EXPRESS_ABLATION_ONLY",
    ),
)


def _from_rows(tag: str, rows) -> Optional[Baseline]:
    b_rows = [r for r in rows if getattr(r, "config", None) == "B" or (isinstance(r, dict) and r.get("config") == "B")]
    if not b_rows and rows:
        # run_resolve_ablation 只跑 B 时 rows 全是 B
        b_rows = list(rows)
    if not b_rows:
        return None
    n = len(b_rows)
    def _ir(r):
        return float(r["items_r"] if isinstance(r, dict) else r.items_r)
    def _ur(r):
        return float(r["union_r"] if isinstance(r, dict) else r.union_r)
    def _passed(r):
        return bool(r["passed"] if isinstance(r, dict) else r.passed)
    return Baseline(
        tag,
        sum(_ir(r) for r in b_rows) / n,
        sum(_ur(r) for r in b_rows) / n,
        sum(1 for r in b_rows if _passed(r)),
        n,
    )


def _summarize_b_file(tag: str) -> Optional[Baseline]:
    path = OUT_DIR / f".tmp_{tag}_ablation_newgt.json"
    if not path.exists():
        path = OUT_DIR / f".tmp_{tag}_ablation_8b_adefg.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return _from_rows(tag, data.get("rows") or [])


async def _run_all() -> None:
    os.environ.setdefault("RESOLVE_CHANNEL_TIMEOUT_MS", "0")
    after: dict[str, Baseline] = {}
    errors: list[str] = []
    for tag, session_cls, cases, clear_env, skip_env, only_env in JOBS:
        print(f"\n######## RUN B: {tag} ########", flush=True)
        os.environ[only_env] = "B"
        os.environ[skip_env] = "1"
        os.environ.pop(clear_env, None)
        try:
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
            got = _from_rows(tag, rows) or _summarize_b_file(tag)
            if got is None:
                errors.append(f"{tag}: missing B summary after run")
            else:
                after[tag] = got
                print(
                    f"[after/{tag}] iR={got.i_r:.0%} uR={got.u_r:.0%} "
                    f"pass={got.passed}/{got.total}",
                    flush=True,
                )
        except Exception as exc:
            errors.append(f"{tag}: {exc}")
            print(f"[ERROR] {tag}: {exc}", flush=True)

    lines = [
        "# 七仓默认 B：排序优化前后对比",
        "",
        "优化点：`ResolveResultPresenter` 查询相关性 / 噪声路径惩罚 / 同族去重。",
        "改前：Design.md §5.12 基线；改后：本次 `skip_rebuild` 只跑 B。",
        "",
        "| 仓 | 改前 iR/uR · pass | 改后 iR/uR · pass | Δ iR | Δ uR | Δ pass |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for b in BEFORE:
        a = after.get(b.tag)
        if a is None:
            lines.append(
                f"| {b.tag} | {b.i_r:.0%}/{b.u_r:.0%} · {b.passed}/{b.total} | "
                f"**失败/缺失** | - | - | - |"
            )
            continue
        di = a.i_r - b.i_r
        du = a.u_r - b.u_r
        dp = a.passed - b.passed
        lines.append(
            f"| {b.tag} | {b.i_r:.0%}/{b.u_r:.0%} · {b.passed}/{b.total} | "
            f"**{a.i_r:.0%}/{a.u_r:.0%} · {a.passed}/{a.total}** | "
            f"{di:+.0%} | {du:+.0%} | {dp:+d} |"
        )
    if errors:
        lines.extend(["", "## Errors", *[f"- {e}" for e in errors]])

    out = OUT_DIR / "_seven_repo_b_before_after.md"
    payload = {
        "before": [b.__dict__ for b in BEFORE],
        "after": {k: v.__dict__ for k, v in after.items()},
        "errors": errors,
    }
    (OUT_DIR / "_seven_repo_b_before_after.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    text = "\n".join(lines) + "\n"
    out.write_text(text, encoding="utf-8")
    print("\n" + text, flush=True)
    print(f"[write] {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(_run_all())
