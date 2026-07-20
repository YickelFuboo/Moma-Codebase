"""NL2Code × 符号摘要 六档消融：重建索引后对比 resolve/related 准确率。

档位：
  A. 符号 ON  + NL2Code OFF + rewrite OFF
  B. 符号 OFF + NL2Code ON  + rewrite OFF
  C. 符号 OFF + NL2Code ON  + rewrite ON（mode=always）
  D. 符号 ON  + NL2Code ON  + rewrite OFF
  E. 符号 ON  + NL2Code ON  + rewrite ON（mode=always）
  F. 符号 ON  + NL2Code ON  + rewrite ON（mode=weak，弱召回才改写）

用法（仓根、venv）：
  PANDO_CLEAR=1 python -m tests.scenarios.pando_agent.run_nl2code_ablation

环境变量：
  PANDO_CLEAR=1（默认）每组索引重建前清库
  PANDO_AGENT_PATH 可选，默认 F:\\Product_Dev\\PANDO\\Pando-Agent
  PANDO_ABLATION_ONLY=F 只跑指定档（逗号分隔）
  PANDO_SKIP_REBUILD=1 跳过清库重建（索引已与目标符号开关一致时）
  PANDO_ABLATION_KIND=resolve|related|all（默认 all）
"""
from __future__ import annotations
import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.pando_agent.ground_truth import PANDO_RELATED_CASES, PANDO_RESOLVE_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


@dataclass
class AblationConfig:
    label: str
    symbol_on: bool
    nl2code: bool
    nl_rewrite: bool
    rewrite_mode: str = "always"


@dataclass
class CaseRow:
    config: str
    case_id: str
    kind: str
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
    AblationConfig("A", symbol_on=True, nl2code=False, nl_rewrite=False),
    AblationConfig("B", symbol_on=False, nl2code=True, nl_rewrite=False),
    AblationConfig("C", symbol_on=False, nl2code=True, nl_rewrite=True, rewrite_mode="always"),
    AblationConfig("D", symbol_on=True, nl2code=True, nl_rewrite=False),
    AblationConfig("E", symbol_on=True, nl2code=True, nl_rewrite=True, rewrite_mode="always"),
    AblationConfig("F", symbol_on=True, nl2code=True, nl_rewrite=True, rewrite_mode="weak"),
]

ALL_LABELS = [c.label for c in CONFIGS]


def _paths(items: List[Dict[str, Any]]) -> List[str]:
    return [str(it.get("file_path")) for it in items if it.get("file_path")]


def _apply_config(cfg: AblationConfig) -> None:
    from app.config.settings import settings
    from app.repo_analysis.services.nl2code_enhance.lexicon import RepoIdentifierLexicon

    PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = cfg.symbol_on
    PandoAgentScenarioSession.apply_feature_flags()
    settings.code_analysis_nl_to_code_enabled = bool(cfg.nl2code)
    settings.code_analysis_nl_rewrite_enabled = bool(cfg.nl_rewrite)
    settings.code_analysis_nl_rewrite_mode = str(cfg.rewrite_mode or "always")
    RepoIdentifierLexicon.cache_clear()
    print(
        f"[flags] {cfg.label}: symbol={cfg.symbol_on} nl2code={cfg.nl2code} "
        f"rewrite={cfg.nl_rewrite} mode={settings.code_analysis_nl_rewrite_mode}",
        flush=True,
    )


async def _rebuild_index(symbol_on: bool) -> str:
    """清库并按 symbol 开关重建待测仓索引。"""
    os.environ["PANDO_CLEAR"] = "1"
    PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = symbol_on
    PandoAgentScenarioSession.CLEAR_BEFORE_ANALYZE = False
    PandoAgentScenarioSession._vector_ready = False
    PandoAgentScenarioSession._graph_ready = False
    # 保留 session repo_id，避免重复登记；仅强制重分析
    print(
        f"\n===== REBUILD index symbol={'ON' if symbol_on else 'OFF'} =====",
        flush=True,
    )
    repo_id = await PandoAgentScenarioSession.ensure_vector_ready()
    os.environ.pop("PANDO_CLEAR", None)
    return repo_id


async def _eval_resolve(cfg: AblationConfig) -> List[CaseRow]:
    from app.repo_analysis.services.search_resolve import SearchResolveService

    _apply_config(cfg)
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
        row = CaseRow(
            config=cfg.label,
            case_id=case.case_id,
            kind="resolve",
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
            trigger = row.nl_rewrite_meta.get("trigger") if isinstance(row.nl_rewrite_meta, dict) else None
            rw = f"Y:{trigger}" if trigger else "Y"
        print(
            f"[{cfg.label}/resolve] {case.case_id} "
            f"iR={row.items_r:.0%} uR={row.union_r:.0%} rw={rw} "
            f"top={row.top} pass={row.passed}",
            flush=True,
        )
    return rows


async def _eval_related(cfg: AblationConfig) -> List[CaseRow]:
    _apply_config(cfg)
    await PandoAgentScenarioSession.ensure_repo()
    rows: List[CaseRow] = []
    for case in PANDO_RELATED_CASES:
        result = None
        last_err: Optional[BaseException] = None
        for attempt in range(1, 4):
            try:
                result = await PandoAgentScenarioSession.search_related(
                    case.extra["keywords"],
                    top_k=case.top_k,
                )
                last_err = None
                break
            except BaseException as exc:
                last_err = exc
                print(
                    f"[{cfg.label}/related] retry {attempt}/3 {case.case_id}: {exc}",
                    flush=True,
                )
                await asyncio.sleep(2.0 * attempt)
        if result is None:
            raise RuntimeError(f"related failed after retries: {case.case_id}") from last_err
        items = result.get("items") or []
        also = result.get("also_consider") or []
        hits = _paths(items)
        also_hits = _paths(also)
        union = hits + [p for p in also_hits if p not in hits]
        score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
        union_score = AccuracyMetrics.evaluate(f"{case.case_id}.union", union, case.expected_paths)
        channels = result.get("channels") or {}
        active = [k for k, v in channels.items() if v] if isinstance(channels, dict) else []
        row = CaseRow(
            config=cfg.label,
            case_id=case.case_id,
            kind="related",
            items_p=score.precision,
            items_r=score.recall,
            union_p=union_score.precision,
            union_r=union_score.recall,
            n_items=len(hits),
            n_also=len(also_hits),
            top=hits[0] if hits else None,
            passed=score.recall >= case.min_recall,
            channels=active,
            nl_rewrite_meta=result.get("nl_rewrite"),
        )
        rows.append(row)
        print(
            f"[{cfg.label}/related] {case.case_id} "
            f"iR={row.items_r:.0%} uR={row.union_r:.0%} "
            f"top={row.top} pass={row.passed}",
            flush=True,
        )
    return rows


def _avg(rows: List[CaseRow], attr: str) -> float:
    return sum(getattr(r, attr) for r in rows) / max(len(rows), 1)


def _print_summary(all_rows: List[CaseRow]) -> None:
    print("\n===== SUMMARY (by config × kind) =====", flush=True)
    print(
        f"{'cfg':<4} {'kind':<8} {'avg_iR':>7} {'avg_uR':>7} {'pass':>8} "
        f"{'symbol':>7} {'nl2c':>5} {'rewr':>5} {'mode':>6}",
        flush=True,
    )
    cfg_map = {c.label: c for c in CONFIGS}
    present = [lbl for lbl in ALL_LABELS if any(r.config == lbl for r in all_rows)]
    for label in present:
        cfg = cfg_map[label]
        mode = cfg.rewrite_mode if cfg.nl_rewrite else "-"
        for kind in ("resolve", "related"):
            rows = [r for r in all_rows if r.config == label and r.kind == kind]
            if not rows:
                continue
            print(
                f"{label:<4} {kind:<8} "
                f"{_avg(rows, 'items_r'):>6.0%} {_avg(rows, 'union_r'):>6.0%} "
                f"{sum(1 for r in rows if r.passed)}/{len(rows):<4} "
                f"{'ON' if cfg.symbol_on else 'OFF':>7} "
                f"{'ON' if cfg.nl2code else 'OFF':>5} "
                f"{'ON' if cfg.nl_rewrite else 'OFF':>5} "
                f"{mode:>6}",
                flush=True,
            )

    print("\n===== FOCUS resolve NL cases (unionR) =====", flush=True)
    focus = {
        "pando.resolve.nl.semantic.memory",
        "pando.resolve.nl.cn_auth",
        "pando.resolve.nl.cn_memory",
        "pando.resolve.nl.cn_ws",
        "pando.resolve.related.BaseAgent",
        "pando.resolve.related.EmbeddingModelFactory",
    }
    hdr = f"{'case':<40}" + "".join(f" {lbl:>6}" for lbl in present)
    print(hdr, flush=True)
    for cid in sorted(focus):
        vals = []
        for label in present:
            hit = next(
                (r for r in all_rows if r.config == label and r.case_id == cid),
                None,
            )
            vals.append(f"{hit.union_r:.0%}" if hit else "-")
        print(f"{cid:<40}" + "".join(f" {v:>6}" for v in vals), flush=True)


async def main() -> None:
    if "PANDO_CLEAR" not in os.environ:
        os.environ["PANDO_CLEAR"] = "1"
    PandoAgentScenarioSession.require_repo_or_skip()
    only = (os.environ.get("PANDO_ABLATION_ONLY") or "").strip().upper()
    skip_rebuild = os.environ.get("PANDO_SKIP_REBUILD", "").strip() in {"1", "true", "True"}
    kind = (os.environ.get("PANDO_ABLATION_KIND") or "all").strip().lower()
    do_resolve = kind in {"all", "resolve"}
    do_related = kind in {"all", "related"}

    print(
        "[nl2code-ablation] A=symbol+noNL | B=noSymbol+NL | "
        "C=noSymbol+NL+rewrite(always) | D=symbol+NL | "
        "E=symbol+NL+rewrite(always) | F=symbol+NL+rewrite(weak) "
        f"only={only or 'ALL'} kind={kind} skip_rebuild={skip_rebuild} "
        f"resolve_cases={len(PANDO_RESOLVE_CASES)}",
        flush=True,
    )

    all_rows: List[CaseRow] = []
    want = set(only.replace(",", " ").split()) if only else set(ALL_LABELS)
    want.discard("")

    async def _eval_cfg(cfg: AblationConfig) -> None:
        print(f"\n--- eval config {cfg.label} ---", flush=True)
        if do_resolve:
            all_rows.extend(await _eval_resolve(cfg))
        if do_related:
            all_rows.extend(await _eval_related(cfg))

    # 组1：无符号索引 → B、C
    no_symbol = {c.label for c in CONFIGS if not c.symbol_on}
    if want & no_symbol:
        if not skip_rebuild:
            await _rebuild_index(symbol_on=False)
        else:
            PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = False
            PandoAgentScenarioSession._vector_ready = True
            await PandoAgentScenarioSession.ensure_repo()
        for cfg in CONFIGS:
            if cfg.symbol_on or cfg.label not in want:
                continue
            await _eval_cfg(cfg)

    # 组2：有符号索引 → A、D、E、F
    with_symbol = {c.label for c in CONFIGS if c.symbol_on}
    if want & with_symbol:
        if not skip_rebuild:
            await _rebuild_index(symbol_on=True)
        else:
            PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = True
            PandoAgentScenarioSession._vector_ready = True
            await PandoAgentScenarioSession.ensure_repo()
        for cfg in CONFIGS:
            if (not cfg.symbol_on) or cfg.label not in want:
                continue
            await _eval_cfg(cfg)

    _print_summary(all_rows)


if __name__ == "__main__":
    asyncio.run(main())
