"""KnowledegBase-Service：resolve 第二真仓评测（默认产品档 D）。

档位（与 Pando 消融对齐）：
  D. 符号 ON + NL2Code ON + rewrite OFF（产品默认）
  F. 符号 ON + NL2Code ON + rewrite ON（mode=weak）

用法：
  KB_CLEAR=1 python -m tests.scenarios.knowledge_base.run_resolve_eval
  KB_SKIP_REBUILD=1 KB_ABLATION_ONLY=D python -m tests.scenarios.knowledge_base.run_resolve_eval

环境变量：
  KB_SERVICE_PATH 可选
  KB_CLEAR=1 清库重建
  KB_SKIP_REBUILD=1 跳过重建（索引已含符号摘要时）
  KB_ABLATION_ONLY=D,F 子集
"""
from __future__ import annotations
import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.knowledge_base.ground_truth import KB_RESOLVE_CASES
from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession


@dataclass
class AblationConfig:
    label: str
    symbol_on: bool
    nl2code: bool
    nl_rewrite: bool
    rewrite_mode: str = "weak"


@dataclass
class CaseRow:
    config: str
    case_id: str
    items_p: float
    items_r: float
    union_p: float
    union_r: float
    n_items: int
    n_also: int
    top: Optional[str]
    passed: bool
    channels: List[str] = field(default_factory=list)
    nl_rewrite_meta: Optional[Dict[str, object]] = None


CONFIGS = [
    AblationConfig("D", symbol_on=True, nl2code=True, nl_rewrite=False),
    AblationConfig("F", symbol_on=True, nl2code=True, nl_rewrite=True, rewrite_mode="weak"),
]

ALL_LABELS = [c.label for c in CONFIGS]


def _paths(items: List[Dict[str, Any]]) -> List[str]:
    return [str(it.get("file_path")) for it in items if it.get("file_path")]


def _apply_config(cfg: AblationConfig) -> None:
    from app.config.settings import settings
    from app.repo_analysis.services.nl2code_enhance.lexicon import RepoIdentifierLexicon

    KnowledgeBaseScenarioSession.ENABLE_SYMBOL_SUMMARY = cfg.symbol_on
    KnowledgeBaseScenarioSession.apply_feature_flags()
    settings.code_analysis_nl_to_code_enabled = bool(cfg.nl2code)
    settings.code_analysis_nl_rewrite_enabled = bool(cfg.nl_rewrite)
    settings.code_analysis_nl_rewrite_mode = str(cfg.rewrite_mode or "weak")
    RepoIdentifierLexicon.cache_clear()
    print(
        f"[flags] {cfg.label}: symbol={cfg.symbol_on} nl2code={cfg.nl2code} "
        f"rewrite={cfg.nl_rewrite} mode={settings.code_analysis_nl_rewrite_mode}",
        flush=True,
    )


async def _rebuild_index() -> str:
    os.environ["KB_CLEAR"] = "1"
    KnowledgeBaseScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    KnowledgeBaseScenarioSession.CLEAR_BEFORE_ANALYZE = False
    KnowledgeBaseScenarioSession._vector_ready = False
    print("\n===== REBUILD KB index symbol=ON =====", flush=True)
    repo_id = await KnowledgeBaseScenarioSession.ensure_vector_ready()
    os.environ.pop("KB_CLEAR", None)
    return repo_id


async def _eval_resolve(cfg: AblationConfig) -> List[CaseRow]:
    from app.repo_analysis.services.search_resolve import SearchResolveService

    _apply_config(cfg)
    repo_id = await KnowledgeBaseScenarioSession.ensure_repo()
    rows: List[CaseRow] = []
    for case in KB_RESOLVE_CASES:
        result = await SearchResolveService.resolve(
            repo_id,
            case.extra["query"],
            top_k=case.top_k,
            intent="auto",
        )
        items = result.get("items") or []
        also = result.get("also_consider") or []
        hits = _paths(items)
        also_hits = _paths(also)
        union = hits + [p for p in also_hits if p not in hits]
        score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
        union_score = AccuracyMetrics.evaluate(f"{case.case_id}.union", union, case.expected_paths)
        row = CaseRow(
            config=cfg.label,
            case_id=case.case_id,
            items_p=score.precision,
            items_r=score.recall,
            union_p=union_score.precision,
            union_r=union_score.recall,
            n_items=len(hits),
            n_also=len(also_hits),
            top=hits[0] if hits else None,
            passed=score.recall >= case.min_recall,
            channels=list(result.get("channels_used") or []),
            nl_rewrite_meta=result.get("nl_rewrite"),
        )
        rows.append(row)
        rw = "N"
        if row.nl_rewrite_meta:
            trigger = (
                row.nl_rewrite_meta.get("trigger")
                if isinstance(row.nl_rewrite_meta, dict)
                else None
            )
            rw = f"Y:{trigger}" if trigger else "Y"
        print(
            f"[{cfg.label}/resolve] {case.case_id} "
            f"iR={row.items_r:.0%} uR={row.union_r:.0%} rw={rw} "
            f"top={row.top} pass={row.passed}",
            flush=True,
        )
    return rows


def _avg(rows: List[CaseRow], attr: str) -> float:
    return sum(getattr(r, attr) for r in rows) / max(len(rows), 1)


def _print_summary(all_rows: List[CaseRow]) -> None:
    print("\n===== KB RESOLVE SUMMARY =====", flush=True)
    print(
        f"{'cfg':<4} {'avg_iR':>7} {'avg_uR':>7} {'pass':>8} "
        f"{'nl2c':>5} {'rewr':>5} {'mode':>6}",
        flush=True,
    )
    cfg_map = {c.label: c for c in CONFIGS}
    present = [lbl for lbl in ALL_LABELS if any(r.config == lbl for r in all_rows)]
    for label in present:
        cfg = cfg_map[label]
        rows = [r for r in all_rows if r.config == label]
        mode = cfg.rewrite_mode if cfg.nl_rewrite else "-"
        print(
            f"{label:<4} {_avg(rows, 'items_r'):>6.0%} {_avg(rows, 'union_r'):>6.0%} "
            f"{sum(1 for r in rows if r.passed)}/{len(rows):<4} "
            f"{'ON' if cfg.nl2code else 'OFF':>5} "
            f"{'ON' if cfg.nl_rewrite else 'OFF':>5} "
            f"{mode:>6}",
            flush=True,
        )

    print("\n===== FOCUS Chinese NL (unionR) =====", flush=True)
    focus = [c.case_id for c in KB_RESOLVE_CASES if ".nl.cn_" in c.case_id]
    hdr = f"{'case':<40}" + "".join(f" {lbl:>6}" for lbl in present)
    print(hdr, flush=True)
    for cid in focus:
        vals = []
        for label in present:
            hit = next((r for r in all_rows if r.config == label and r.case_id == cid), None)
            vals.append(f"{hit.union_r:.0%}" if hit else "-")
        print(f"{cid:<40}" + "".join(f" {v:>6}" for v in vals), flush=True)


async def main() -> None:
    KnowledgeBaseScenarioSession.require_repo_or_skip()
    only = (os.environ.get("KB_ABLATION_ONLY") or "").strip().upper()
    skip_rebuild = os.environ.get("KB_SKIP_REBUILD", "").strip() in {"1", "true", "True"}
    want = set(only.replace(",", " ").split()) if only else set(ALL_LABELS)
    want.discard("")

    print(
        f"[kb-resolve-eval] D=default | F=weak-rewrite "
        f"only={only or 'ALL'} skip_rebuild={skip_rebuild} "
        f"cases={len(KB_RESOLVE_CASES)} path={KnowledgeBaseScenarioSession.codebase_path()}",
        flush=True,
    )

    if not skip_rebuild:
        await _rebuild_index()
    else:
        KnowledgeBaseScenarioSession.ENABLE_SYMBOL_SUMMARY = True
        KnowledgeBaseScenarioSession._vector_ready = True
        await KnowledgeBaseScenarioSession.ensure_repo()

    all_rows: List[CaseRow] = []
    for cfg in CONFIGS:
        if cfg.label not in want:
            continue
        print(f"\n--- eval config {cfg.label} ---", flush=True)
        all_rows.extend(await _eval_resolve(cfg))
    _print_summary(all_rows)


if __name__ == "__main__":
    asyncio.run(main())
