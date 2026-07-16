"""集合准确率：Precision / Recall；向量检索可侧重 Recall@k。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set


def normalize_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


def to_path_set(paths: Iterable[str], *, prefix: Optional[str] = "app/") -> Set[str]:
    result: Set[str] = set()
    for raw in paths:
        p = normalize_path(str(raw))
        if not p:
            continue
        if prefix and not p.startswith(prefix):
            continue
        result.add(p)
    return result


@dataclass
class AccuracyScore:
    case_id: str
    precision: float
    recall: float
    hit_count: int
    expected_count: int
    matched_count: int
    hits: List[str] = field(default_factory=list)
    expected: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    extra: List[str] = field(default_factory=list)

    @property
    def f1(self) -> float:
        if self.precision + self.recall <= 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)


class AccuracyMetrics:
    """集合准确率：Precision / Recall。"""

    _scores: List[AccuracyScore] = []

    @classmethod
    def reset(cls) -> None:
        cls._scores = []

    @classmethod
    def evaluate(
        cls,
        case_id: str,
        hits: Iterable[str],
        expected: Iterable[str],
        *,
        prefix: Optional[str] = "app/",
    ) -> AccuracyScore:
        h = to_path_set(hits, prefix=prefix)
        e = to_path_set(expected, prefix=prefix)
        matched = h & e
        precision = (len(matched) / len(h)) if h else 0.0
        recall = (len(matched) / len(e)) if e else 0.0
        score = AccuracyScore(
            case_id=case_id,
            precision=precision,
            recall=recall,
            hit_count=len(h),
            expected_count=len(e),
            matched_count=len(matched),
            hits=sorted(h),
            expected=sorted(e),
            missing=sorted(e - h),
            extra=sorted(h - e),
        )
        cls._scores.append(score)
        return score

    @classmethod
    def assert_pass(
        cls,
        score: AccuracyScore,
        *,
        min_precision: float = 0.6,
        min_recall: float = 0.6,
        require_precision: bool = True,
    ) -> None:
        assert score.expected_count > 0, f"{score.case_id}: 期望集合为空"
        assert score.recall >= min_recall, (
            f"{score.case_id}: Recall={score.recall:.2%} < {min_recall:.0%}; "
            f"hits={score.hits} expected={score.expected} missing={score.missing}"
        )
        if require_precision:
            assert score.precision >= min_precision, (
                f"{score.case_id}: Precision={score.precision:.2%} < {min_precision:.0%}; "
                f"hits={score.hits} expected={score.expected} extra={score.extra}"
            )

    @classmethod
    def summary_lines(cls) -> List[str]:
        if not cls._scores:
            return ["[accuracy] no cases"]
        avg_p = sum(s.precision for s in cls._scores) / len(cls._scores)
        avg_r = sum(s.recall for s in cls._scores) / len(cls._scores)
        lines = [
            f"[accuracy] cases={len(cls._scores)} avg_precision={avg_p:.2%} avg_recall={avg_r:.2%}",
        ]
        for s in cls._scores:
            lines.append(
                f"  - {s.case_id}: P={s.precision:.2%} R={s.recall:.2%} "
                f"hit={s.hit_count} expect={s.expected_count} matched={s.matched_count}"
            )
        return lines

    @classmethod
    def print_summary(cls) -> None:
        for line in cls.summary_lines():
            print(line)
