"""符号摘要开/关消融：同一索引上对比 resolve / related。

用法（仓根、venv）：
  python -m tests.scenarios.pando_agent.run_symbol_summary_ablation

默认 PANDO_CLEAR=0，复用已有分析，不重跑 analyze。
"""
from __future__ import annotations
import asyncio
import os
from dataclasses import dataclass
from typing import Any, Dict, List
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_RELATED_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession
from tests.scenarios.pando_agent.test_resolve_accuracy import PANDO_RESOLVE_CASES


@dataclass
class CaseRow:
    case_id: str
    kind: str
    symbol_on: bool
    channels: List[str]
    channel_errors: Dict[str, str]
    items_p: float
    items_r: float
    union_p: float
    union_r: float
    n_items: int
    n_also: int
    top: str | None
    passed: bool


def _paths(items: List[Dict[str, Any]]) -> List[str]:
    return [str(it.get("file_path")) for it in items if it.get("file_path")]


async def _eval_resolve(symbol_on: bool) -> List[CaseRow]:
    from app.repo_analysis.services.search_resolve import SearchResolveService

    PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = symbol_on
    PandoAgentScenarioSession.apply_feature_flags()
    repo_id = await PandoAgentScenarioSession.ensure_repo()
    rows: List[CaseRow] = []
    for case in PANDO_RESOLVE_CASES:
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
        passed = score.recall >= case.min_recall and (
            score.precision >= case.min_precision or not case.extra.get("require_precision", False)
        )
        if case.extra.get("require_precision", False) is False:
            passed = score.recall >= case.min_recall
        row = CaseRow(
            case_id=case.case_id,
            kind="resolve",
            symbol_on=symbol_on,
            channels=list(result.get("channels_used") or []),
            channel_errors=dict(result.get("channel_errors") or {}),
            items_p=score.precision,
            items_r=score.recall,
            union_p=union_score.precision,
            union_r=union_score.recall,
            n_items=len(hits),
            n_also=len(also_hits),
            top=hits[0] if hits else None,
            passed=passed,
        )
        rows.append(row)
        print(
            f"[resolve symbol={'ON' if symbol_on else 'OFF'}] {case.case_id} "
            f"ch={row.channels} itemsR={row.items_r:.0%} unionR={row.union_r:.0%} "
            f"top={row.top} pass={row.passed}",
            flush=True,
        )
    return rows


async def _eval_related(symbol_on: bool) -> List[CaseRow]:
    PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = symbol_on
    PandoAgentScenarioSession.apply_feature_flags()
    await PandoAgentScenarioSession.ensure_repo()
    rows: List[CaseRow] = []
    for case in PANDO_RELATED_CASES:
        result = await PandoAgentScenarioSession.search_related(
            case.extra["keywords"],
            top_k=case.top_k,
        )
        items = result.get("items") or []
        also = result.get("also_consider") or []
        hits = _paths(items)
        also_hits = _paths(also)
        union = hits + [p for p in also_hits if p not in hits]
        score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
        union_score = AccuracyMetrics.evaluate(f"{case.case_id}.union", union, case.expected_paths)
        channels = result.get("channels") or {}
        active = [k for k, v in channels.items() if v] if isinstance(channels, dict) else []
        passed = score.recall >= case.min_recall
        row = CaseRow(
            case_id=case.case_id,
            kind="related",
            symbol_on=symbol_on,
            channels=active,
            channel_errors={},
            items_p=score.precision,
            items_r=score.recall,
            union_p=union_score.precision,
            union_r=union_score.recall,
            n_items=len(hits),
            n_also=len(also_hits),
            top=hits[0] if hits else None,
            passed=passed,
        )
        rows.append(row)
        print(
            f"[related symbol={'ON' if symbol_on else 'OFF'}] {case.case_id} "
            f"flags={row.channels} itemsR={row.items_r:.0%} unionR={row.union_r:.0%} "
            f"top={row.top} pass={row.passed}",
            flush=True,
        )
    return rows


def _print_compare(on_rows: List[CaseRow], off_rows: List[CaseRow], title: str) -> None:
    print(f"\n===== {title} =====", flush=True)
    print(
        f"{'case':<42} {'ON_ch':<22} {'OFF_ch':<18} "
        f"{'ON_iR':>6} {'OFF_iR':>6} {'ON_uR':>6} {'OFF_uR':>6} {'ΔuR':>6} {'pass':>8}",
        flush=True,
    )
    on_map = {r.case_id: r for r in on_rows}
    for off in off_rows:
        on = on_map[off.case_id]
        delta = off.union_r - on.union_r
        print(
            f"{off.case_id:<42} "
            f"{','.join(on.channels)[:20]:<22} "
            f"{','.join(off.channels)[:16]:<18} "
            f"{on.items_r:>5.0%} {off.items_r:>5.0%} "
            f"{on.union_r:>5.0%} {off.union_r:>5.0%} "
            f"{delta:>+5.0%} "
            f"{'Y' if on.passed else 'N'}→{'Y' if off.passed else 'N':>1}",
            flush=True,
        )
    avg = lambda rows, attr: sum(getattr(r, attr) for r in rows) / max(len(rows), 1)
    print(
        f"{'AVG':<42} {'':<22} {'':<18} "
        f"{avg(on_rows, 'items_r'):>5.0%} {avg(off_rows, 'items_r'):>5.0%} "
        f"{avg(on_rows, 'union_r'):>5.0%} {avg(off_rows, 'union_r'):>5.0%} "
        f"{avg(off_rows, 'union_r') - avg(on_rows, 'union_r'):>+5.0%} "
        f"{sum(1 for r in on_rows if r.passed)}/{len(on_rows)}→"
        f"{sum(1 for r in off_rows if r.passed)}/{len(off_rows)}",
        flush=True,
    )


async def main() -> None:
    os.environ["PANDO_CLEAR"] = "0"
    PandoAgentScenarioSession.CLEAR_BEFORE_ANALYZE = False
    PandoAgentScenarioSession.require_repo_or_skip()

    # 先 ON：必要时建索引（仅一次）
    PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = True
    await PandoAgentScenarioSession.ensure_vector_ready()

    print("\n--- symbol ON ---", flush=True)
    resolve_on = await _eval_resolve(True)
    related_on = await _eval_related(True)

    print("\n--- symbol OFF (reuse index) ---", flush=True)
    resolve_off = await _eval_resolve(False)
    related_off = await _eval_related(False)

    _print_compare(resolve_on, resolve_off, "RESOLVE ON vs OFF")
    _print_compare(related_on, related_off, "RELATED ON vs OFF (OFF=path_fallback)")


if __name__ == "__main__":
    asyncio.run(main())
