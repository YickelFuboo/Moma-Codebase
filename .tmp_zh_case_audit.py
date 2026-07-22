from pathlib import Path
import re

ASCII_CODEISH = re.compile(
    r"[A-Za-z]{2,}|"  # any latin word 2+
    r"[A-Z][a-z]+[A-Z]|"  # Camel
    r"[a-z]+_[a-z]+"  # snake
)


def classify_query(q: str) -> str:
    q = (q or "").strip()
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", q))
    has_latin = bool(re.search(r"[A-Za-z]", q))
    if has_cjk and not has_latin:
        return "pure_zh"
    if has_cjk and has_latin:
        return "zh_mix"
    if has_latin and not has_cjk:
        return "en_only"
    return "other"


def show(path: str, var: str) -> None:
    ns: dict = {}
    exec(Path(path).read_text(encoding="utf-8"), ns)
    cases = ns[var]
    buckets = {"pure_zh": [], "zh_mix": [], "en_only": [], "other": []}
    for c in cases:
        q = (c.extra or {}).get("query", "")
        b = classify_query(q)
        buckets[b].append((c.case_id.rsplit(".", 1)[-1], (c.extra or {}).get("case_kind", "?"), q.replace("\n", " / ")[:100]))
    print(f"== {var} total={len(cases)} ==")
    for b in ("pure_zh", "zh_mix", "en_only", "other"):
        print(f"  {b}: {len(buckets[b])}")
        for short, kind, q in buckets[b]:
            if b in ("pure_zh", "zh_mix"):
                print(f"    [{kind}] {short}: {q!r}")
    print()


show("tests/scenarios/pando_agent/ground_truth.py", "PANDO_RESOLVE_CASES")
show("tests/scenarios/knowledge_base/ground_truth.py", "KB_RESOLVE_CASES")
show("tests/scenarios/go_oss/ground_truth.py", "GO_RESOLVE_CASES")
show("tests/scenarios/django_oss/ground_truth.py", "DJANGO_RESOLVE_CASES")
