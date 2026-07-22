import json
from collections import defaultdict
from pathlib import Path

repos = {
    "pando": (
        "tests/scenarios/pando_agent/ground_truth.py",
        "PANDO_RESOLVE_CASES",
        ".tmp_pando_ablation_newgt.json",
    ),
    "kb": (
        "tests/scenarios/knowledge_base/ground_truth.py",
        "KB_RESOLVE_CASES",
        ".tmp_kb_ablation_newgt.json",
    ),
    "go": (
        "tests/scenarios/go_oss/ground_truth.py",
        "GO_RESOLVE_CASES",
        ".tmp_go_ablation_newgt.json",
    ),
    "django": (
        "tests/scenarios/django_oss/ground_truth.py",
        "DJANGO_RESOLVE_CASES",
        ".tmp_django_ablation_newgt.json",
    ),
}


def load_kinds(gt_path: str, var: str) -> dict:
    ns: dict = {}
    exec(Path(gt_path).read_text(encoding="utf-8"), ns)
    cases = ns[var]
    return {c.case_id: (c.extra or {}).get("case_kind", "?") for c in cases}


def avg(xs, key):
    return sum(x[key] for x in xs) / len(xs)


def pstr(xs):
    return f"{sum(1 for x in xs if x['passed'])}/{len(xs)}"


print(
    f"{'repo':<8} {'kind':<8} {'n':>3}  "
    f"{'A_pass':>7} {'D_pass':>7} {'F_pass':>7}  "
    f"{'A_iR':>6} {'D_iR':>6} {'F_iR':>6}  "
    f"{'A_uR':>6} {'D_uR':>6} {'F_uR':>6}"
)
for name, (gt, var, art) in repos.items():
    kinds = load_kinds(gt, var)
    rows = json.loads(Path(art).read_text(encoding="utf-8"))["rows"]
    by = defaultdict(list)
    for r in rows:
        if r["config"] not in ("A", "D", "F"):
            continue
        k = kinds.get(r["case_id"], "?")
        by[(k, r["config"])].append(r)
    for kind in ("sym", "sym_nl", "nl", "similar", "hard"):
        a = by.get((kind, "A"), [])
        d = by.get((kind, "D"), [])
        f = by.get((kind, "F"), [])
        if not a:
            continue
        print(
            f"{name:<8} {kind:<8} {len(a):>3}  "
            f"{pstr(a):>7} {pstr(d):>7} {pstr(f):>7}  "
            f"{avg(a, 'items_r'):>5.0%} {avg(d, 'items_r'):>5.0%} {avg(f, 'items_r'):>5.0%}  "
            f"{avg(a, 'union_r'):>5.0%} {avg(d, 'union_r'):>5.0%} {avg(f, 'union_r'):>5.0%}"
        )
    print("  -- A vs D diffs on nl/sym_nl/hard --")
    for r_a in rows:
        if r_a["config"] != "A":
            continue
        k = kinds.get(r_a["case_id"], "?")
        if k not in ("nl", "sym_nl", "hard"):
            continue
        r_d = next(x for x in rows if x["config"] == "D" and x["case_id"] == r_a["case_id"])
        if r_a["passed"] != r_d["passed"] or abs(r_a["items_r"] - r_d["items_r"]) > 0.01:
            short = r_a["case_id"].split(".")[-1]
            print(
                f"  {short:<28} kind={k:<7} "
                f"A iR={r_a['items_r']:.0%} pass={r_a['passed']} | "
                f"D iR={r_d['items_r']:.0%} pass={r_d['passed']} | "
                f"AuR={r_a['union_r']:.0%} DuR={r_d['union_r']:.0%}"
            )
    print()
