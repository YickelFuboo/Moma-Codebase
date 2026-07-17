from __future__ import annotations
import re
from typing import Dict, List, Set
from app.repo_analysis.services.codevector.similar_query import SimilarQueryNormalizer


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")


class SimilarRerankService:
    """similar 向量召回后的 lexical + 符号名加权 rerank。"""

    VECTOR_WEIGHT = 0.55
    LEXICAL_WEIGHT = 0.35
    SYMBOL_WEIGHT = 0.10

    @classmethod
    def rerank(
        cls,
        docs: List[Dict[str, object]],
        query_text: str,
        symbol_names: Set[str],
    ) -> List[Dict[str, object]]:
        if not docs:
            return []
        normalized_query = SimilarQueryNormalizer.normalize(query_text)
        query_tokens = cls._tokenize(normalized_query)
        ranked: List[Dict[str, object]] = []
        for doc in docs:
            content = str(doc.get("content") or "")
            vec_score = cls._as_float(doc.get("_score"))
            lex_score = cls._lexical_overlap(query_tokens, cls._tokenize(content))
            sym_score = cls._symbol_overlap(symbol_names, content)
            fused = (
                vec_score * cls.VECTOR_WEIGHT
                + lex_score * cls.LEXICAL_WEIGHT
                + sym_score * cls.SYMBOL_WEIGHT
            )
            item = dict(doc)
            item["_fused_score"] = fused
            item["_lexical_score"] = lex_score
            item["_symbol_score"] = sym_score
            ranked.append(item)
        ranked.sort(
            key=lambda it: (
                -float(it.get("_fused_score") or 0),
                -float(it.get("_score") or 0),
                str(it.get("file_path") or ""),
            )
        )
        return cls._dedupe_by_file(ranked)

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        return set(_TOKEN.findall(text or ""))

    @staticmethod
    def _lexical_overlap(query_tokens: Set[str], candidate_tokens: Set[str]) -> float:
        if not query_tokens:
            return 0.0
        if not candidate_tokens:
            return 0.0
        return len(query_tokens & candidate_tokens) / len(query_tokens)

    @staticmethod
    def _symbol_overlap(symbol_names: Set[str], content: str) -> float:
        if not symbol_names or not content:
            return 0.0
        hits = sum(1 for name in symbol_names if name in content)
        return min(1.0, hits / max(len(symbol_names), 1))

    @staticmethod
    def _dedupe_by_file(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
        best: Dict[str, Dict[str, object]] = {}
        for it in items:
            fp = str(it.get("file_path") or "")
            if not fp:
                continue
            prev = best.get(fp)
            if prev is None or float(it.get("_fused_score") or 0) > float(prev.get("_fused_score") or 0):
                best[fp] = it
        return sorted(
            best.values(),
            key=lambda it: (-float(it.get("_fused_score") or 0), str(it.get("file_path") or "")),
        )

    @staticmethod
    def _as_float(value: object) -> float:
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0
