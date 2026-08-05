"""九仓 B/E/G/F 重跑（skip rebuild），与 Design §5.12 排序优化前基线对比。

用法（项目根）：
  poetry run python -m tests.scenarios.mid_oss.run_befg_before_after
  poetry run python -m tests.scenarios.mid_oss.run_befg_before_after --only pando,kb,nng
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
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
from tests.scenarios.oss_common.resolve_eval import ALL_CONFIGS, AblationConfig, CaseRow, run_resolve_ablation
from tests.scenarios.pando_agent.ground_truth import PANDO_RESOLVE_CASES
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession
from tests.scenarios.spdlog_oss.ground_truth import SPDLOG_RESOLVE_CASES
from tests.scenarios.spdlog_oss.session_support import SpdlogOssScenarioSession


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "tests" / "output"
CFG_ORDER = ("B", "E", "G", "F")


@dataclass(frozen=True)
class Score:
    i_r: float
    u_r: float
    passed: int
    total: int

    def fmt(self) -> str:
        return f"{self.passed}/{self.total} · {self.i_r:.0%}/{self.u_r:.0%}"


# Design.md §5.12 排序优化前快照（A–G 表）
BEFORE: Dict[str, Dict[str, Score]] = {
    "pando": {
        "B": Score(0.86, 0.91, 19, 22),
        "E": Score(0.91, 0.95, 20, 22),
        "G": Score(0.89, 0.95, 20, 22),
        "F": Score(0.93, 0.95, 21, 22),
    },
    "kb": {
        "B": Score(0.71, 0.88, 12, 17),
        "E": Score(0.71, 0.88, 12, 17),
        "G": Score(0.76, 1.00, 13, 17),
        "F": Score(0.76, 0.94, 13, 17),
    },
    "go": {
        "B": Score(0.58, 0.89, 20, 32),
        "E": Score(0.58, 0.78, 20, 32),
        "G": Score(0.58, 0.78, 20, 32),
        "F": Score(0.61, 0.88, 20, 32),
    },
    "django": {
        "B": Score(0.85, 0.98, 28, 33),
        "E": Score(0.73, 0.95, 24, 33),
        "G": Score(0.74, 0.94, 25, 33),
        "F": Score(0.80, 0.97, 27, 33),
    },
    "hcl": {
        "B": Score(0.58, 0.77, 21, 32),
        "E": Score(0.54, 0.74, 22, 32),
        "G": Score(0.56, 0.77, 23, 32),
        "F": Score(0.58, 0.81, 23, 32),
    },
    "nng": {
        "B": Score(0.55, 0.80, 24, 32),
        "E": Score(0.53, 0.70, 24, 32),
        "G": Score(0.53, 0.72, 24, 32),
        "F": Score(0.45, 0.61, 20, 32),
    },
    "spdlog": {
        "B": Score(0.41, 0.71, 18, 32),
        "E": Score(0.31, 0.69, 15, 32),
        "G": Score(0.27, 0.66, 12, 32),
        "F": Score(0.31, 0.62, 14, 32),
    },
    "gson": {
        "B": Score(0.72, 0.90, 24, 32),
        "E": Score(0.41, 0.87, 14, 32),
        "G": Score(0.41, 0.87, 14, 32),
        "F": Score(0.46, 0.90, 16, 32),
    },
    "express": {
        "B": Score(0.64, 1.00, 21, 32),
        "E": Score(0.70, 1.00, 23, 32),
        "G": Score(0.70, 1.00, 23, 32),
        "F": Score(0.97, 0.98, 32, 32),
    },
}

JOBS: Tuple = (
    ("pando", PandoAgentScenarioSession, PANDO_RESOLVE_CASES, "PANDO_CLEAR", "PANDO_SKIP_REBUILD", "PANDO_ABLATION_ONLY"),
    ("kb", KnowledgeBaseScenarioSession, KB_RESOLVE_CASES, "KB_CLEAR", "KB_SKIP_REBUILD", "KB_ABLATION_ONLY"),
    ("go", GoOssScenarioSession, GO_RESOLVE_CASES, "GO_CLEAR", "GO_SKIP_REBUILD", "GO_ABLATION_ONLY"),
    ("django", DjangoOssScenarioSession, DJANGO_RESOLVE_CASES, "DJANGO_CLEAR", "DJANGO_SKIP_REBUILD", "DJANGO_ABLATION_ONLY"),
    ("hcl", HclOssScenarioSession, HCL_RESOLVE_CASES, "HCL_CLEAR", "HCL_SKIP_REBUILD", "HCL_ABLATION_ONLY"),
    ("nng", NngOssScenarioSession, NNG_RESOLVE_CASES, "NNG_CLEAR", "NNG_SKIP_REBUILD", "NNG_ABLATION_ONLY"),
    ("spdlog", SpdlogOssScenarioSession, SPDLOG_RESOLVE_CASES, "SPDLOG_CLEAR", "SPDLOG_SKIP_REBUILD", "SPDLOG_ABLATION_ONLY"),
    ("gson", GsonOssScenarioSession, GSON_RESOLVE_CASES, "GSON_CLEAR", "GSON_SKIP_REBUILD", "GSON_ABLATION_ONLY"),
    ("express", ExpressOssScenarioSession, EXPRESS_RESOLVE_CASES, "EXPRESS_CLEAR", "EXPRESS_SKIP_REBUILD", "EXPRESS_ABLATION_ONLY"),
)


def _configs() -> List[AblationConfig]:
    by_label = {c.label: c for c in ALL_CONFIGS}
    return [by_label[x] for x in CFG_ORDER]


def _score_rows(rows: Sequence[CaseRow], label: str) -> Optional[Score]:
    subset = [r for r in rows if r.config == label]
    if not subset:
        return None
    n = len(subset)
    return Score(
        sum(float(r.items_r) for r in subset) / n,
        sum(float(r.union_r) for r in subset) / n,
        sum(1 for r in subset if r.passed),
        n,
    )


def _load_existing_after() -> Dict[str, Dict[str, Score]]:
    """合并历史 after，便于 --only 续跑时保留已完成仓。"""
    path = OUT / "_nine_repo_befg_before_after.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, Dict[str, Score]] = {}
    for tag, cfgs in (raw.get("after") or {}).items():
        scores: Dict[str, Score] = {}
        for cfg, d in (cfgs or {}).items():
            if not isinstance(d, dict):
                continue
            scores[cfg] = Score(
                float(d["i_r"]),
                float(d["u_r"]),
                int(d["passed"]),
                int(d["total"]),
            )
        if scores:
            out[tag] = scores
    return out


def _delta_cell(before: Score, after: Score) -> str:
    dp = after.passed - before.passed
    sign = f"{dp:+d}" if dp != 0 else "0"
    return (
        f"{after.fmt()} "
        f"(ΔiR {after.i_r - before.i_r:+.0%} ΔuR {after.u_r - before.u_r:+.0%} Δpass {sign})"
    )


def _write_report(
    after: Dict[str, Dict[str, Score]],
    errors: List[str],
) -> Path:
    # 写入前再合并磁盘结果，降低并行 --only 互相覆盖的风险
    merged = _load_existing_after()
    merged.update(after)
    after.clear()
    after.update(merged)
    lines = [
        "# 九仓 B/E/G/F：检索排序优化前后对比",
        "",
        "改前：Design.md §5.12 排序优化前 A–G 快照；改后：本次 skip_rebuild 重跑（含 `ResolveResultPresenter` 排序）。",
        "档位：B=符号 · E=符号+NL · G=符号+NL+weak · F=符号+NL+always。",
        "",
    ]
    for cfg in CFG_ORDER:
        lines.extend(
            [
                f"## 档位 {cfg}",
                "",
                "| 仓 | 改前 iR/uR · pass | 改后（含 Δ） |",
                "| --- | --- | --- |",
            ]
        )
        for tag, *_ in JOBS:
            b = BEFORE[tag][cfg]
            a = (after.get(tag) or {}).get(cfg)
            if a is None:
                lines.append(f"| {tag} | {b.fmt()} | **未跑/失败** |")
            else:
                lines.append(f"| {tag} | {b.fmt()} | **{_delta_cell(b, a)}** |")
        lines.append("")

    lines.extend(
        [
            "## 总表（改后 pass / 改前 pass）",
            "",
            "| 仓 | B | E | G | F |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for tag, *_ in JOBS:
        cells = []
        for cfg in CFG_ORDER:
            b = BEFORE[tag][cfg]
            a = (after.get(tag) or {}).get(cfg)
            if a is None:
                cells.append("-")
            else:
                cells.append(f"{a.passed}/{a.total} ({a.passed - b.passed:+d})")
        lines.append(f"| {tag} | " + " | ".join(cells) + " |")
    lines.append("")
    if errors:
        lines.extend(["## Errors", *[f"- {e}" for e in errors], ""])

    OUT.mkdir(parents=True, exist_ok=True)
    md_path = OUT / "_nine_repo_befg_before_after.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    (OUT / "_nine_repo_befg_before_after.json").write_text(
        json.dumps(
            {
                "before": {t: {c: asdict(s) for c, s in m.items()} for t, m in BEFORE.items()},
                "after": {t: {c: asdict(s) for c, s in m.items()} for t, m in after.items()},
                "errors": errors,
                "configs": list(CFG_ORDER),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("\n" + "\n".join(lines), flush=True)
    print(f"[write] {md_path}", flush=True)
    return md_path


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        default="",
        help="逗号分隔仓名：pando,kb,go,django,hcl,nng,spdlog,gson,express",
    )
    parser.add_argument(
        "--configs",
        default="",
        help="逗号分隔档位，默认 B,E,G,F；例：G 或 B,E",
    )
    args = parser.parse_args()
    want = {x.strip().lower() for x in (args.only or "").split(",") if x.strip()}
    os.environ.setdefault("RESOLVE_CHANNEL_TIMEOUT_MS", "0")
    cfg_want = [x.strip().upper() for x in (args.configs or "").split(",") if x.strip()]
    if cfg_want:
        by_label = {c.label: c for c in ALL_CONFIGS}
        bad = [x for x in cfg_want if x not in by_label]
        if bad:
            raise SystemExit(f"unknown --configs: {bad}; choose from {list(CFG_ORDER)}")
        configs = [by_label[x] for x in cfg_want]
    else:
        configs = _configs()
    labels = ",".join(c.label for c in configs)
    after: Dict[str, Dict[str, Score]] = _load_existing_after()
    errors: List[str] = []
    if after:
        print(
            f"[resume] loaded after for: {', '.join(sorted(after.keys()))}",
            flush=True,
        )

    for tag, session_cls, cases, clear_env, skip_env, only_env in JOBS:
        if want and tag not in want:
            continue
        print(f"\n######## {tag.upper()} {labels} ########", flush=True)
        try:
            session_cls.require_repo_or_skip()
            os.environ[only_env] = labels
            os.environ[skip_env] = "1"
            os.environ.pop(clear_env, None)
            session_cls._vector_ready = True
            rows = await run_resolve_ablation(
                session_cls=session_cls,
                cases=cases,
                tag=tag,
                clear_env=clear_env,
                skip_env=skip_env,
                only_env=only_env,
                configs=configs,
            )
            prev = dict(after.get(tag) or {})
            scores: Dict[str, Score] = dict(prev)
            for cfg in (c.label for c in configs):
                s = _score_rows(rows, cfg)
                if s is None:
                    errors.append(f"{tag}/{cfg}: missing rows")
                    continue
                scores[cfg] = s
                b = BEFORE[tag][cfg]
                print(
                    f"[after/{tag}/{cfg}] {s.fmt()}  vs before {b.fmt()}  "
                    f"Δpass={s.passed - b.passed:+d}",
                    flush=True,
                )
            after[tag] = scores
        except Exception as exc:
            errors.append(f"{tag}: {exc}")
            print(f"[ERROR] {tag}: {exc}", flush=True)
        _write_report(after, errors)


if __name__ == "__main__":
    asyncio.run(main())
