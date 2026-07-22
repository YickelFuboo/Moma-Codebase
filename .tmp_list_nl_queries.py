from pathlib import Path


def show(path: str, var: str) -> None:
    ns: dict = {}
    exec(Path(path).read_text(encoding="utf-8"), ns)
    cases = ns[var]
    print("==", var, "==")
    for c in cases:
        k = (c.extra or {}).get("case_kind", "?")
        if k not in ("nl", "hard", "sym_nl"):
            continue
        q = (c.extra or {}).get("query", "")
        q1 = q.replace("\n", " / ")[:140]
        short = c.case_id.rsplit(".", 1)[-1]
        print(f"  [{k}] {short}: {q1!r}")
    print()


show("tests/scenarios/pando_agent/ground_truth.py", "PANDO_RESOLVE_CASES")
show("tests/scenarios/knowledge_base/ground_truth.py", "KB_RESOLVE_CASES")
show("tests/scenarios/go_oss/ground_truth.py", "GO_RESOLVE_CASES")
show("tests/scenarios/django_oss/ground_truth.py", "DJANGO_RESOLVE_CASES")
