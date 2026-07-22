import json
import re
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


def is_pure_zh(q: str) -> bool:
    q = (q or "").strip()
    return bool(re.search(r"[\u4e00-\u9fff]", q)) and not bool(re.search(r"[A-Za-z]", q))


def load_cases(gt_path: str, var: str):
    ns: dict = {}
    exec(Path(gt_path).read_text(encoding="utf-8"), ns)
    return ns[var]


print(
    f"{'repo':<8} {'case':<28} {'A_iR':>5} {'D_iR':>5} {'A_uR':>5} {'D_uR':>5} "
    f"{'A_pass':>6} {'D_pass':>6}  query"
)
print("-" * 120)

tot = {"A_pass": 0, "D_pass": 0, "n": 0, "A_better": 0, "D_better": 0, "tie": 0}
for name, (gt, var, art) in repos.items():
    cases = load_cases(gt, var)
    rows = json.loads(Path(art).read_text(encoding="utf-8"))["rows"]
    by = {(r["case_id"], r["config"]): r for r in rows}
    for c in cases:
        q = (c.extra or {}).get("query", "")
        if not is_pure_zh(q):
            continue
        a = by[(c.case_id, "A")]
        d = by[(c.case_id, "D")]
        short = c.case_id.rsplit(".", 1)[-1]
        q1 = q.replace("\n", " ")[:40]
        print(
            f"{name:<8} {short:<28} {a['items_r']:>4.0%} {d['items_r']:>4.0%} "
            f"{a['union_r']:>4.0%} {d['union_r']:>4.0%} "
            f"{str(a['passed']):>6} {str(d['passed']):>6}  {q1}"
        )
        tot["n"] += 1
        tot["A_pass"] += int(a["passed"])
        tot["D_pass"] += int(d["passed"])
        if a["passed"] and not d["passed"]:
            tot["A_better"] += 1
        elif d["passed"] and not a["passed"]:
            tot["D_better"] += 1
        elif a["items_r"] != d["items_r"] or a["union_r"] != d["union_r"]:
            # soft diff without pass flip
            if (d["items_r"], d["union_r"]) > (a["items_r"], a["union_r"]):
                tot["D_better"] += 0  # counted only on pass flip for clarity
            tot["tie"] += 1  # same pass outcome
        else:
            tot["tie"] += 1

print("-" * 120)
print(
    f"pure_zh n={tot['n']}: A_pass={tot['A_pass']}/{tot['n']}  "
    f"D_pass={tot['D_pass']}/{tot['n']}  "
    f"pass翻转 D胜A={tot['D_better']} A胜D={tot['A_better']}"
)
