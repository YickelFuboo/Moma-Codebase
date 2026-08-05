"""按仓串行：CLEAR 重分析后跑 A–G，并与 Design §5.12 总表对比。

用法（项目根）：
  poetry run python -m tests.scenarios.mid_oss.run_reanalyze_ag_queue --only express
  poetry run python -m tests.scenarios.mid_oss.run_reanalyze_ag_queue --only gson,nng
"""
from __future__ import annotations
import argparse
import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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
from tests.scenarios.knowledge_base.ground_truth import KB_RESOLVE_CASES
from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession
from tests.scenarios.nng_oss.ground_truth import NNG_RESOLVE_CASES
from tests.scenarios.nng_oss.session_support import NngOssScenarioSession
from tests.scenarios.oss_common.resolve_eval import ALL_CONFIGS, CaseRow, run_resolve_ablation
from tests.scenarios.pando_agent.ground_truth import PANDO_RESOLVE_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession
from tests.scenarios.spdlog_oss.ground_truth import SPDLOG_RESOLVE_CASES
from tests.scenarios.spdlog_oss.session_support import SpdlogOssScenarioSession


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "tests" / "output"
COMPARE = OUT / "_reanalyze_ag_queue_compare.md"

# Design §5.12 当前总表快照（已 CLEAR 仓用 After；Go/Django 仍为 07-25 排序后）
DESIGN_BEFORE: Dict[str, Dict[str, Tuple[float, float, int, int]]] = {
    "express": {
        "A": (0.86, 0.98, 29, 32),
        "B": (0.94, 1.00, 32, 32),
        "C": (0.84, 0.98, 29, 32),
        "D": (0.86, 0.98, 28, 32),
        "E": (0.94, 1.00, 32, 32),
        "F": (0.97, 0.98, 32, 32),
        "G": (0.91, 1.00, 31, 32),
    },
    "gson": {
        "A": (0.70, 0.94, 25, 32),
        "B": (0.83, 0.95, 29, 32),
        "C": (0.67, 0.94, 24, 32),
        "D": (0.64, 0.93, 22, 32),
        "E": (0.62, 0.91, 22, 32),
        "F": (0.64, 0.91, 23, 32),
        "G": (0.62, 0.91, 22, 32),
    },
    "nng": {
        "A": (0.43, 0.62, 22, 32),
        "B": (0.57, 0.81, 28, 32),
        "C": (0.52, 0.66, 24, 32),
        "D": (0.49, 0.70, 23, 32),
        "E": (0.54, 0.72, 25, 32),
        "F": (0.51, 0.66, 22, 32),
        "G": (0.54, 0.72, 24, 32),
    },
    "go": {
        "A": (0.19, 0.56, 7, 32),
        "B": (0.58, 0.89, 20, 32),
        "C": (0.31, 0.58, 11, 32),
        "D": (0.39, 0.66, 14, 32),
        "E": (0.61, 0.80, 22, 32),
        "F": (0.66, 0.84, 23, 32),
        "G": (0.58, 0.73, 21, 32),
    },
    "django": {
        "A": (0.24, 0.64, 8, 33),
        "B": (0.82, 0.95, 27, 33),
        "C": (0.40, 0.78, 14, 33),
        "D": (0.36, 0.68, 12, 33),
        "E": (0.73, 0.95, 24, 33),
        "F": (0.65, 0.97, 22, 33),
        "G": (0.74, 0.94, 25, 33),
    },
    "kb": {
        "A": (0.35, 0.76, 6, 17),
        "B": (0.76, 0.88, 13, 17),
        "C": (0.88, 0.94, 15, 17),
        "D": (0.76, 0.82, 13, 17),
        "E": (0.76, 0.88, 13, 17),
        "F": (0.76, 0.94, 13, 17),
        "G": (0.76, 1.00, 13, 17),
    },
    "pando": {
        "A": (0.68, 0.86, 15, 22),
        "B": (0.86, 0.93, 19, 22),
        "C": (0.75, 1.00, 17, 22),
        "D": (0.80, 0.95, 18, 22),
        "E": (0.95, 0.98, 21, 22),
        "F": (0.84, 0.86, 19, 22),
        "G": (0.93, 0.95, 21, 22),
    },
    "hcl": {
        "A": (0.34, 0.59, 13, 32),
        "B": (0.56, 0.78, 21, 32),
        "C": (0.48, 0.55, 18, 32),
        "D": (0.53, 0.66, 19, 32),
        "E": (0.60, 0.80, 24, 32),
        "F": (0.69, 0.86, 27, 32),
        "G": (0.66, 0.81, 26, 32),
    },
    "spdlog": {
        "A": (0.31, 0.47, 16, 32),
        "B": (0.48, 0.78, 24, 32),
        "C": (0.38, 0.52, 19, 32),
        "D": (0.31, 0.53, 15, 32),
        "E": (0.34, 0.70, 19, 32),
        "F": (0.33, 0.66, 18, 32),
        "G": (0.33, 0.67, 18, 32),
    },
}

JOBS = (
    ("express", ExpressOssScenarioSession, EXPRESS_RESOLVE_CASES, "EXPRESS_CLEAR", "EXPRESS_SKIP_REBUILD", "EXPRESS_ABLATION_ONLY"),
    ("gson", GsonOssScenarioSession, GSON_RESOLVE_CASES, "GSON_CLEAR", "GSON_SKIP_REBUILD", "GSON_ABLATION_ONLY"),
    ("nng", NngOssScenarioSession, NNG_RESOLVE_CASES, "NNG_CLEAR", "NNG_SKIP_REBUILD", "NNG_ABLATION_ONLY"),
    ("go", GoOssScenarioSession, GO_RESOLVE_CASES, "GO_CLEAR", "GO_SKIP_REBUILD", "GO_ABLATION_ONLY"),
    ("django", DjangoOssScenarioSession, DJANGO_RESOLVE_CASES, "DJANGO_CLEAR", "DJANGO_SKIP_REBUILD", "DJANGO_ABLATION_ONLY"),
    ("kb", KnowledgeBaseScenarioSession, KB_RESOLVE_CASES, "KB_CLEAR", "KB_SKIP_REBUILD", "KB_ABLATION_ONLY"),
    ("pando", PandoAgentScenarioSession, PANDO_RESOLVE_CASES, "PANDO_CLEAR", "PANDO_SKIP_REBUILD", "PANDO_ABLATION_ONLY"),
    ("hcl", HclOssScenarioSession, HCL_RESOLVE_CASES, "HCL_CLEAR", "HCL_SKIP_REBUILD", "HCL_ABLATION_ONLY"),
    ("spdlog", SpdlogOssScenarioSession, SPDLOG_RESOLVE_CASES, "SPDLOG_CLEAR", "SPDLOG_SKIP_REBUILD", "SPDLOG_ABLATION_ONLY"),
)


@dataclass(frozen=True)
class Score:
    i_r: float
    u_r: float
    passed: int
    total: int

    def fmt(self) -> str:
        return f"{self.passed}/{self.total} · {self.i_r:.0%}/{self.u_r:.0%}"


def _score_rows(rows: List[CaseRow], cfg: str) -> Optional[Score]:
    sub = [r for r in rows if r.config == cfg]
    if not sub:
        return None
    n = len(sub)
    return Score(
        sum(float(r.items_r) for r in sub) / n,
        sum(float(r.union_r) for r in sub) / n,
        sum(1 for r in sub if r.passed),
        n,
    )


async def _rebuild(tag: str, session_cls, clear_env: str) -> str:
    from app.repo_analysis.services.file_analysis_service import FileAnalysisService

    os.environ[clear_env] = "1"
    session_cls.ENABLE_SYMBOL_SUMMARY = True
    session_cls._vector_ready = False
    try:
        await FileAnalysisService.stop_global_scheduler()
    except Exception:
        pass
    for other_id in list(getattr(FileAnalysisService, "_running_tasks", {}).keys()):
        try:
            await FileAnalysisService.stop_analysis(other_id)
        except Exception:
            pass
    print(f"[rebuild] {tag} path={session_cls.codebase_path()} clear=1", flush=True)
    repo_id = await session_cls.ensure_vector_ready()
    os.environ.pop(clear_env, None)
    print(f"[rebuild] {tag} done repo_id={repo_id}", flush=True)
    return str(repo_id)


def _append_compare(tag: str, after: Dict[str, Score], rebuilt: bool) -> None:
    before = DESIGN_BEFORE.get(tag) or {}
    lines = [
        f"## {tag.upper()}（{'CLEAR重分析' if rebuilt else '仅评测'}）",
        "| 档 | Design 前 | 本次 After | Δpass |",
        "| --- | --- | --- | --- |",
    ]
    for cfg in "ABCDEFG":
        a = after.get(cfg)
        b = before.get(cfg)
        if a is None:
            lines.append(f"| {cfg} | — | 缺失 | — |")
            continue
        if b is None:
            lines.append(f"| {cfg} | — | **{a.fmt()}** | — |")
            continue
        d_ir, d_ur, d_p, d_t = b
        dlt = a.passed - d_p
        lines.append(
            f"| {cfg} | {d_p}/{d_t} · {d_ir:.0%}/{d_ur:.0%} | **{a.fmt()}** | {dlt:+d} |"
        )
    lines.append("")
    prev = COMPARE.read_text(encoding="utf-8") if COMPARE.exists() else "# 九仓 CLEAR 重分析 / 评测 vs Design\n\n"
    # 替换同仓旧块
    block = "\n".join(lines) + "\n"
    pat = re.compile(rf"## {re.escape(tag.upper())}（.*?）\n(?:\|.*\n)+\n?", re.S)
    if pat.search(prev):
        prev = pat.sub(block, prev, count=1)
    else:
        prev = prev.rstrip() + "\n\n" + block
    COMPARE.write_text(prev, encoding="utf-8")
    print(f"[write] {COMPARE}", flush=True)
    print(block, flush=True)


async def _run_one(tag: str, session_cls, cases, clear_env: str, skip_env: str, only_env: str, *, rebuild: bool) -> None:
    labels = "A,B,C,D,E,F,G"
    os.environ[only_env] = labels
    os.environ.setdefault("RESOLVE_CHANNEL_TIMEOUT_MS", "0")
    if rebuild:
        await _rebuild(tag, session_cls, clear_env)
    os.environ[skip_env] = "1"
    session_cls._vector_ready = True
    session_cls.ENABLE_SYMBOL_SUMMARY = True
    print(f"\n########## {tag.upper()} {labels} (rebuild={rebuild}) ##########", flush=True)
    session_cls.require_repo_or_skip()
    rows = await run_resolve_ablation(
        session_cls=session_cls,
        cases=cases,
        tag=tag,
        clear_env=clear_env,
        skip_env=skip_env,
        only_env=only_env,
        configs=list(ALL_CONFIGS),
    )
    after: Dict[str, Score] = {}
    for cfg in "ABCDEFG":
        s = _score_rows(rows, cfg)
        if s is not None:
            after[cfg] = s
            print(f"[after/{tag}/{cfg}] {s.fmt()}", flush=True)
    _append_compare(tag, after, rebuilt=rebuild)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", required=True, help="逗号分隔仓名")
    parser.add_argument(
        "--skip-rebuild",
        default="",
        help="逗号分隔：这些仓跳过 CLEAR（已重建过）",
    )
    args = parser.parse_args()
    want = [x.strip().lower() for x in args.only.split(",") if x.strip()]
    skip_rebuild = {x.strip().lower() for x in (args.skip_rebuild or "").split(",") if x.strip()}
    by_tag = {j[0]: j for j in JOBS}
    for tag in want:
        if tag not in by_tag:
            raise SystemExit(f"unknown tag {tag}; choose from {sorted(by_tag)}")
        j = by_tag[tag]
        await _run_one(*j, rebuild=tag not in skip_rebuild)


if __name__ == "__main__":
    asyncio.run(main())
