"""开源大仓 resolve 评测共用逻辑（含 A–F 消融）。

符号摘要开关在**查询时**生效：关则不走 match_symbols / 符号向量，
只走 path_fallback（行块路径）+ similar 行块。因此 A–F 对比
**不必**为 B/C 清库重建无符号索引；复用已有（含符号）索引即可。
"""
from __future__ import annotations
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Type
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.framework.case_spec import PathSetCase


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
    elapsed_ms: float = 0.0


# 与 Pando §5.12 对齐：A=符号 B=NL C=NL+always D=符号+NL E=符号+NL+always F=符号+NL+weak
ALL_CONFIGS: List[AblationConfig] = [
    AblationConfig("A", symbol_on=True, nl2code=False, nl_rewrite=False),
    AblationConfig("B", symbol_on=False, nl2code=True, nl_rewrite=False),
    AblationConfig("C", symbol_on=False, nl2code=True, nl_rewrite=True, rewrite_mode="always"),
    AblationConfig("D", symbol_on=True, nl2code=True, nl_rewrite=False),
    AblationConfig("E", symbol_on=True, nl2code=True, nl_rewrite=True, rewrite_mode="always"),
    AblationConfig("F", symbol_on=True, nl2code=True, nl_rewrite=True, rewrite_mode="weak"),
]

# 评测顺序：先有符号通道档，再关符号档（均不重建索引）
EVAL_ORDER = ("A", "D", "E", "F", "B", "C")

DEFAULT_D = next(c for c in ALL_CONFIGS if c.label == "D")


def paths(items: List[Dict[str, Any]]) -> List[str]:
    return [str(it.get("file_path")) for it in items if it.get("file_path")]


def apply_config(cfg: AblationConfig, session_cls: Type) -> None:
    from app.config.settings import settings
    from app.repo_analysis.services.nl2code_enhance.lexicon import RepoIdentifierLexicon

    session_cls.ENABLE_SYMBOL_SUMMARY = cfg.symbol_on
    session_cls.apply_feature_flags()
    settings.code_analysis_nl_to_code_enabled = bool(cfg.nl2code)
    settings.code_analysis_nl_rewrite_enabled = bool(cfg.nl_rewrite)
    settings.code_analysis_nl_rewrite_mode = str(cfg.rewrite_mode or "weak")
    RepoIdentifierLexicon.cache_clear()
    print(
        f"[flags] {cfg.label}: symbol={cfg.symbol_on} nl2code={cfg.nl2code} "
        f"rewrite={cfg.nl_rewrite} mode={settings.code_analysis_nl_rewrite_mode}",
        flush=True,
    )


async def eval_resolve(
    *,
    cfg: AblationConfig,
    session_cls: Type,
    cases: Sequence[PathSetCase],
    tag: str,
) -> List[CaseRow]:
    from app.repo_analysis.services.search_resolve import SearchResolveService

    apply_config(cfg, session_cls)
    repo_id = await session_cls.ensure_repo()
    rows: List[CaseRow] = []
    for case in cases:
        t0 = time.perf_counter()
        result = await SearchResolveService.resolve(
            repo_id,
            case.extra["query"],
            top_k=case.top_k,
            intent="auto",
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        items = result.get("items") or []
        also = result.get("also_consider") or []
        hits = paths(items)
        also_hits = paths(also)
        union = hits + [p for p in also_hits if p not in hits]
        score = AccuracyMetrics.evaluate(
            case.case_id, hits, case.expected_paths, prefix=None
        )
        union_score = AccuracyMetrics.evaluate(
            f"{case.case_id}.union", union, case.expected_paths, prefix=None
        )
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
            elapsed_ms=elapsed_ms,
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
            f"[{tag}/{cfg.label}] {case.case_id} "
            f"iR={row.items_r:.0%} uR={row.union_r:.0%} rw={rw} "
            f"ms={row.elapsed_ms:.0f} top={row.top} pass={row.passed}",
            flush=True,
        )
    return rows


def avg(rows: List[CaseRow], attr: str) -> float:
    return sum(getattr(r, attr) for r in rows) / max(len(rows), 1)


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[idx]


def print_latency_table(tag: str, all_rows: List[CaseRow]) -> None:
    present = [lbl for lbl in EVAL_ORDER if any(r.config == lbl for r in all_rows)]
    case_ids = list(dict.fromkeys(r.case_id for r in all_rows))
    print(f"\n===== {tag} CASE LATENCY (ms) =====", flush=True)
    print(
        f"{'case':<52}" + "".join(f" {lbl:>8}" for lbl in present) + f" {'avg':>8}",
        flush=True,
    )
    for cid in case_ids:
        vals: List[str] = []
        nums: List[float] = []
        for label in present:
            hit = next((r for r in all_rows if r.config == label and r.case_id == cid), None)
            if hit is None:
                vals.append("-")
            else:
                vals.append(f"{hit.elapsed_ms:.0f}")
                nums.append(hit.elapsed_ms)
        avg_ms = sum(nums) / len(nums) if nums else 0.0
        print(f"{cid:<52}" + "".join(f" {v:>8}" for v in vals) + f" {avg_ms:>8.0f}", flush=True)


def dump_eval_artifact(tag: str, all_rows: List[CaseRow], configs: Sequence[AblationConfig]) -> Path:
    """写出 JSON + Markdown，便于人工检视准确率与耗时。"""
    out_dir = Path(".")
    json_path = out_dir / f".tmp_{tag.lower()}_ablation_newgt.json"
    md_path = out_dir / f".tmp_{tag.lower()}_ablation_newgt.md"
    payload = {
        "tag": tag,
        "rows": [asdict(r) for r in all_rows],
        "summary": [],
    }
    cfg_map = {c.label: c for c in configs}
    lines = [f"# {tag} resolve 消融（新 GT）", ""]
    lines.append("## 档位汇总")
    lines.append("")
    lines.append("| cfg | avg_iR | avg_uR | pass | avg_ms | p50_ms | p95_ms |")
    lines.append("|-----|--------|--------|------|--------|--------|--------|")
    for label in EVAL_ORDER:
        rows = [r for r in all_rows if r.config == label]
        if not rows:
            continue
        ms = [r.elapsed_ms for r in rows]
        summary = {
            "cfg": label,
            "avg_iR": avg(rows, "items_r"),
            "avg_uR": avg(rows, "union_r"),
            "pass": f"{sum(1 for r in rows if r.passed)}/{len(rows)}",
            "avg_ms": avg(rows, "elapsed_ms"),
            "p50_ms": _percentile(ms, 0.50),
            "p95_ms": _percentile(ms, 0.95),
            "symbol": cfg_map[label].symbol_on if label in cfg_map else None,
        }
        payload["summary"].append(summary)
        lines.append(
            f"| {label} | {summary['avg_iR']:.0%} | {summary['avg_uR']:.0%} | "
            f"{summary['pass']} | {summary['avg_ms']:.0f} | "
            f"{summary['p50_ms']:.0f} | {summary['p95_ms']:.0f} |"
        )
    lines.append("")
    lines.append("## 每用例耗时 (ms)")
    lines.append("")
    present = [lbl for lbl in EVAL_ORDER if any(r.config == lbl for r in all_rows)]
    case_ids = list(dict.fromkeys(r.case_id for r in all_rows))
    lines.append("| case | " + " | ".join(present) + " | avg |")
    lines.append("|------|" + "|".join(["------"] * len(present)) + "|-----|")
    for cid in case_ids:
        cells: List[str] = []
        nums: List[float] = []
        for label in present:
            hit = next((r for r in all_rows if r.config == label and r.case_id == cid), None)
            if hit is None:
                cells.append("-")
            else:
                cells.append(f"{hit.elapsed_ms:.0f}")
                nums.append(hit.elapsed_ms)
        avg_ms = sum(nums) / len(nums) if nums else 0.0
        short = cid.split(".")[-1] if cid.count(".") >= 2 else cid
        lines.append(f"| `{short}` | " + " | ".join(cells) + f" | {avg_ms:.0f} |")
    lines.append("")
    lines.append("## 每用例准确率 (iR/pass)")
    lines.append("")
    lines.append("| case | " + " | ".join(f"{lbl} iR" for lbl in present) + " |")
    lines.append("|------|" + "|".join(["------"] * len(present)) + "|")
    for cid in case_ids:
        cells = []
        for label in present:
            hit = next((r for r in all_rows if r.config == label and r.case_id == cid), None)
            if hit is None:
                cells.append("-")
            else:
                mark = "✓" if hit.passed else "✗"
                cells.append(f"{hit.items_r:.0%}{mark}")
        short = cid.split(".")[-1] if cid.count(".") >= 2 else cid
        lines.append(f"| `{short}` | " + " | ".join(cells) + " |")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[{tag}] artifact json={json_path.resolve()}", flush=True)
    print(f"[{tag}] artifact md={md_path.resolve()}", flush=True)
    return md_path


def print_summary(tag: str, all_rows: List[CaseRow], configs: Sequence[AblationConfig]) -> None:
    print(f"\n===== {tag} RESOLVE SUMMARY =====", flush=True)
    print(
        f"{'cfg':<4} {'avg_iR':>7} {'avg_uR':>7} {'pass':>8} {'avg_ms':>8} "
        f"{'p50':>7} {'p95':>7} {'symbol':>7} {'nl2c':>5} {'rewr':>5} {'mode':>6}",
        flush=True,
    )
    cfg_map = {c.label: c for c in configs}
    for label in EVAL_ORDER:
        rows = [r for r in all_rows if r.config == label]
        if not rows:
            continue
        cfg = cfg_map[label]
        mode = cfg.rewrite_mode if cfg.nl_rewrite else "-"
        ms = [r.elapsed_ms for r in rows]
        print(
            f"{label:<4} {avg(rows, 'items_r'):>6.0%} {avg(rows, 'union_r'):>6.0%} "
            f"{sum(1 for r in rows if r.passed)}/{len(rows):<4} "
            f"{avg(rows, 'elapsed_ms'):>7.0f} "
            f"{_percentile(ms, 0.50):>6.0f} {_percentile(ms, 0.95):>6.0f} "
            f"{'ON' if cfg.symbol_on else 'OFF':>7} "
            f"{'ON' if cfg.nl2code else 'OFF':>5} "
            f"{'ON' if cfg.nl_rewrite else 'OFF':>5} "
            f"{mode:>6}",
            flush=True,
        )
    print_latency_table(tag, all_rows)
    focus = [r.case_id for r in all_rows if ".nl.cn_" in r.case_id or ".hard." in r.case_id]
    focus = list(dict.fromkeys(focus))
    present = [lbl for lbl in EVAL_ORDER if any(r.config == lbl for r in all_rows)]
    if focus:
        print(f"\n===== {tag} FOCUS NL/hard (unionR) =====", flush=True)
        print(f"{'case':<52}" + "".join(f" {lbl:>6}" for lbl in present), flush=True)
        for cid in focus:
            vals = []
            for label in present:
                hit = next((r for r in all_rows if r.config == label and r.case_id == cid), None)
                vals.append(f"{hit.union_r:.0%}" if hit else "-")
            print(f"{cid:<52}" + "".join(f" {v:>6}" for v in vals), flush=True)
    dump_eval_artifact(tag, all_rows, configs)


def env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip() in {"1", "true", "True"}


def parse_only(raw: str, default: Sequence[str] = EVAL_ORDER) -> set[str]:
    text = (raw or "").strip().upper()
    if not text or text in {"ALL", "*"}:
        return set(default)
    want = set(text.replace(",", " ").split())
    want.discard("")
    return want


async def run_resolve_ablation(
    *,
    session_cls: Type,
    cases: Sequence[PathSetCase],
    tag: str,
    clear_env: str,
    skip_env: str,
    only_env: str,
    configs: Sequence[AblationConfig] = ALL_CONFIGS,
) -> List[CaseRow]:
    """A–F resolve 消融：默认复用已有索引，仅切换查询时开关。"""
    session_cls.require_repo_or_skip()
    skip = env_truthy(skip_env) or not env_truthy(clear_env)
    want = parse_only(os.environ.get(only_env, "ALL"))
    ordered = [c for c in configs if c.label in want]
    ordered.sort(key=lambda c: EVAL_ORDER.index(c.label) if c.label in EVAL_ORDER else 99)

    print(
        f"[{tag}-resolve-eval] only={[c.label for c in ordered]} "
        f"skip_rebuild={skip} cases={len(cases)} "
        f"path={session_cls.codebase_path()} "
        f"note=query-time flags only (no symbol-off rebuild)",
        flush=True,
    )

    if not skip:
        os.environ[clear_env] = "1"
        session_cls.ENABLE_SYMBOL_SUMMARY = True
        session_cls._vector_ready = False
        await session_cls.ensure_vector_ready()
        os.environ.pop(clear_env, None)
    else:
        session_cls.ENABLE_SYMBOL_SUMMARY = True
        session_cls._vector_ready = True
        await session_cls.ensure_repo()

    all_rows: List[CaseRow] = []
    for cfg in ordered:
        print(f"\n--- eval config {cfg.label} ---", flush=True)
        all_rows.extend(
            await eval_resolve(cfg=cfg, session_cls=session_cls, cases=cases, tag=tag)
        )
    print_summary(tag.upper(), all_rows, configs)
    return all_rows
