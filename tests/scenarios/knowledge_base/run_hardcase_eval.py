"""难例评测：可跳过 analyze，直接用现有索引打 baseline。"""
from __future__ import annotations
import argparse
import asyncio
import os
from typing import Iterable, List
from tests.scenarios.framework.accuracy import AccuracyMetrics
from tests.scenarios.framework.case_spec import PathSetCase
from tests.scenarios.knowledge_base.ground_truth import (
    KB_RELATED_CASES,
    KB_SIMILAR_CASES,
    KB_SIMILAR_WEAK_CASES,
)
from tests.scenarios.knowledge_base.session_support import KnowledgeBaseScenarioSession
from tests.scenarios.pando_agent.ground_truth import (
    PANDO_RELATED_CASES,
    PANDO_SIMILAR_CASES,
    PANDO_SIMILAR_WEAK_CASES,
)
from tests.scenarios.pando_agent.session_support import PandoAgentScenarioSession


def _hard_related(cases: Iterable[PathSetCase]) -> List[PathSetCase]:
    return [c for c in cases if "hard" in c.case_id or "semantic" in c.case_id]


async def _eval_related(session_cls, cases: List[PathSetCase], tag: str) -> None:
    for case in cases:
        result = await session_cls.search_related(case.extra["keywords"], top_k=case.top_k)
        items = result.get("items") or []
        hits = [it.get("file_path") for it in items]
        score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
        top = hits[0] if hits else None
        top1_ok = bool(top and any(e.replace("\\", "/") in str(top).replace("\\", "/") for e in case.expected_paths))
        print(
            f"[{tag}-related] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
            f"top1_ok={top1_ok} top={top}",
            flush=True,
        )


async def _eval_similar(session_cls, cases: List[PathSetCase], tag: str) -> None:
    for case in cases:
        result = await session_cls.search_similar(case.extra["code"], top_k=case.top_k)
        items = result.get("items") or []
        hits = [it.get("file_path") for it in items]
        score = AccuracyMetrics.evaluate(case.case_id, hits, case.expected_paths)
        top = str(items[0].get("file_path") or "").replace("\\", "/") if items else ""
        expected = {p.replace("\\", "/") for p in case.expected_paths}
        print(
            f"[{tag}-similar] {case.case_id} P={score.precision:.2%} R={score.recall:.2%} "
            f"top1_ok={top in expected} top={top}",
            flush=True,
        )


async def run_pando(*, analyze: bool) -> None:
    os.environ["PANDO_CLEAR"] = "0"
    PandoAgentScenarioSession.require_repo_or_skip()
    if analyze:
        PandoAgentScenarioSession.ENABLE_SYMBOL_SUMMARY = True
        PandoAgentScenarioSession.CLEAR_BEFORE_ANALYZE = False
        await PandoAgentScenarioSession.ensure_vector_ready()
    else:
        await PandoAgentScenarioSession.ensure_repo()
        PandoAgentScenarioSession.apply_feature_flags()
        PandoAgentScenarioSession._vector_ready = True
    print("=== PANDO RELATED HARD ===", flush=True)
    await _eval_related(PandoAgentScenarioSession, _hard_related(PANDO_RELATED_CASES), "pando")
    print("=== PANDO SIMILAR STRONG ===", flush=True)
    await _eval_similar(PandoAgentScenarioSession, PANDO_SIMILAR_CASES, "pando")
    print("=== PANDO SIMILAR WEAK ===", flush=True)
    await _eval_similar(PandoAgentScenarioSession, PANDO_SIMILAR_WEAK_CASES, "pando")


async def run_kb(*, analyze: bool) -> None:
    os.environ["KB_CLEAR"] = "0"
    KnowledgeBaseScenarioSession.require_repo_or_skip()
    if analyze:
        KnowledgeBaseScenarioSession.ENABLE_SYMBOL_SUMMARY = True
        KnowledgeBaseScenarioSession.CLEAR_BEFORE_ANALYZE = False
        await KnowledgeBaseScenarioSession.ensure_vector_ready()
    else:
        await KnowledgeBaseScenarioSession.ensure_repo()
        KnowledgeBaseScenarioSession.apply_feature_flags()
        KnowledgeBaseScenarioSession._vector_ready = True
    print("=== KB RELATED ===", flush=True)
    await _eval_related(KnowledgeBaseScenarioSession, KB_RELATED_CASES, "kb")
    print("=== KB SIMILAR STRONG ===", flush=True)
    await _eval_similar(KnowledgeBaseScenarioSession, KB_SIMILAR_CASES, "kb")
    print("=== KB SIMILAR WEAK ===", flush=True)
    await _eval_similar(KnowledgeBaseScenarioSession, KB_SIMILAR_WEAK_CASES, "kb")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", choices=["pando", "kb", "both"], default="both")
    parser.add_argument("--analyze", action="store_true", help="全仓 app analyze（含符号摘要）后再评")
    args = parser.parse_args()
    AccuracyMetrics.reset()
    if args.repo in {"pando", "both"}:
        await run_pando(analyze=args.analyze)
    if args.repo in {"kb", "both"}:
        await run_kb(analyze=args.analyze)
    AccuracyMetrics.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
