from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select
from app.config.settings import settings
from app.infrastructure.database import get_db_session
from app.repo_analysis.services.codevector.exact_match import ExactMatchService
from app.repo_analysis.services.codevector.similar_query import SimilarQueryNormalizer
from app.repo_analysis.services.codevector.similar_rerank import SimilarRerankService
from app.repo_analysis.services.codevector.vector_search import CodeVectorSearchService
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService
from app.repo_analysis.services.search_index_meta import SearchIndexMeta
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


class SearchService:
    """仓库内代码相似检索、关键词关联位置检索、历史经验模式检索。"""

    EXACT_SYMBOL_BOOST = 1.2
    EXACT_SYMBOL_WEAK_BOOST = 0.6
    EXACT_PATH_BOOST = 0.3
    CODEGRAPH_SCORE = 1.0
    # 相对 top1 的分数门槛：低于此比例的条目丢弃（对齐「短列表高精确」）
    SCORE_RATIO_FLOOR = 0.55
    # 存在强符号定义命中时，不再硬凑满 top_k
    STRONG_SYMBOL_CAP = 5
    STRONG_SYMBOL_RAW = 2.8
    SIMILAR_FETCH_MULTIPLIER = 4
    SIMILAR_MIN_FETCH = 40

    @classmethod
    def _merge_similar_docs(
        cls,
        batches: List[List[Dict[str, object]]],
    ) -> List[Dict[str, object]]:
        best: Dict[Tuple[object, object, object], Dict[str, object]] = {}
        for docs in batches:
            for doc in docs:
                key = (
                    doc.get("file_path"),
                    doc.get("start_line"),
                    doc.get("end_line"),
                )
                score = float(doc.get("_score") or 0)
                prev = best.get(key)
                if prev is None or score > float(prev.get("_score") or 0):
                    best[key] = doc
        return list(best.values())

    @classmethod
    def _apply_similar_trim(
        cls,
        items: List[Dict[str, object]],
        top_k: int,
    ) -> List[Dict[str, object]]:
        if not items:
            return []
        top_score = float(items[0].get("score") or 0)
        floor = top_score * cls.SCORE_RATIO_FLOOR
        trimmed = [it for it in items if float(it.get("score") or 0) >= floor]
        if not trimmed:
            trimmed = items[:1]
        return trimmed[: max(1, top_k)]

    @classmethod
    def fuse_similar_items(
        cls,
        docs: List[Dict[str, object]],
        *,
        query_text: str,
        top_k: int,
    ) -> List[Dict[str, object]]:
        symbol_names = SimilarQueryNormalizer.extract_symbol_names(query_text)
        reranked = SimilarRerankService.rerank(docs, query_text, symbol_names)
        items: List[Dict[str, object]] = []
        for doc in reranked:
            items.append(
                {
                    "file_path": doc.get("file_path"),
                    "start_line": doc.get("start_line"),
                    "end_line": doc.get("end_line"),
                    "score": doc.get("_fused_score"),
                    "vector_score": doc.get("_score"),
                    "lexical_score": doc.get("_lexical_score"),
                    "symbol_score": doc.get("_symbol_score"),
                    "match_source": "line_chunk",
                }
            )
        return cls._apply_similar_trim(items, top_k)

    @staticmethod
    def _item_key(it: Dict[str, object]) -> Tuple[object, object, object, object, object]:
        return (
            it.get("file_path"),
            it.get("symbol_kind"),
            it.get("symbol_name"),
            it.get("start_line"),
            it.get("end_line"),
        )

    @classmethod
    def _normalize_vector_item(cls, doc: Dict[str, object], source: str) -> Dict[str, object]:
        score = doc.get("_score")
        try:
            score_f = float(score) if score is not None else 0.5
        except (TypeError, ValueError):
            score_f = 0.5
        return {
            "file_path": doc.get("file_path"),
            "symbol_kind": doc.get("symbol_kind"),
            "symbol_name": doc.get("symbol_name"),
            "start_line": doc.get("start_line"),
            "end_line": doc.get("end_line"),
            "score": score_f,
            "match_source": source,
            "exact_tier": None,
        }

    @classmethod
    def _exact_boost(cls, tier: str) -> float:
        if tier == "symbol":
            return cls.EXACT_SYMBOL_BOOST
        if tier == "symbol_weak":
            return cls.EXACT_SYMBOL_WEAK_BOOST
        return cls.EXACT_PATH_BOOST

    @classmethod
    def _rank_key(cls, item: Dict[str, object]) -> Tuple[int, float, str]:
        source = str(item.get("match_source") or "")
        tier = str(item.get("exact_tier") or "")
        score = float(item.get("score") or 0)
        if source == "exact" and tier == "symbol":
            group = 0
        elif source == "exact" and tier == "symbol_weak":
            group = 1
        elif source == "exact":
            group = 2
        elif source == "codegraph":
            group = 3
        elif source == "mr_experience":
            group = 4
        else:
            group = 5
        return (group, -score, str(item.get("file_path") or ""))

    @classmethod
    def _has_strong_symbol(cls, items: List[Dict[str, object]]) -> bool:
        for it in items:
            if str(it.get("match_source") or "") != "exact":
                continue
            if str(it.get("exact_tier") or "") != "symbol":
                continue
            raw = float(it.get("_raw_score") or 0)
            if raw >= cls.STRONG_SYMBOL_RAW:
                return True
            score = float(it.get("score") or 0)
            if score >= cls.STRONG_SYMBOL_RAW + cls.EXACT_SYMBOL_BOOST - 1e-6:
                return True
        return False

    @classmethod
    def _apply_precision_trim(
        cls,
        unique: List[Dict[str, object]],
        top_k: int,
    ) -> List[Dict[str, object]]:
        if not unique:
            return []
        top_score = float(unique[0].get("score") or 0)
        floor = top_score * cls.SCORE_RATIO_FLOOR
        trimmed = [it for it in unique if float(it.get("score") or 0) >= floor]
        if not trimmed:
            trimmed = unique[:1]
        if cls._has_strong_symbol(trimmed):
            defs = [
                it
                for it in trimmed
                if str(it.get("match_source") or "") == "exact"
                and str(it.get("exact_tier") or "") in {"symbol", "symbol_weak"}
            ]
            if defs:
                trimmed = defs
            cap = min(max(1, top_k), cls.STRONG_SYMBOL_CAP)
            return trimmed[:cap]
        return trimmed[: max(1, top_k)]

    @classmethod
    def fuse_related_items(
        cls,
        *,
        exact_items: List[Dict[str, object]],
        symbol_docs: List[Dict[str, object]],
        top_k: int,
        extra_items: Optional[List[Dict[str, object]]] = None,
    ) -> List[Dict[str, object]]:
        """精确强符号 > 弱符号 > 路径 > 图谱/向量；按文件去重后做分数门槛与强符号截断。"""
        ranked: List[Dict[str, object]] = []
        for it in exact_items:
            raw = float(it.get("_score") or 0)
            tier = str(it.get("exact_tier") or ("symbol" if raw >= 2.8 else "path"))
            boost = cls._exact_boost(tier)
            ranked.append(
                {
                    "file_path": it.get("file_path"),
                    "symbol_kind": it.get("symbol_kind"),
                    "symbol_name": it.get("symbol_name"),
                    "start_line": it.get("start_line"),
                    "end_line": it.get("end_line"),
                    "score": raw + boost,
                    "_raw_score": raw,
                    "match_source": "exact",
                    "exact_tier": tier,
                }
            )
        for doc in symbol_docs:
            ranked.append(cls._normalize_vector_item(doc, "symbol_summary"))
        for it in extra_items or []:
            ranked.append(it)

        ranked.sort(key=cls._rank_key)
        best_by_file: Dict[str, Dict[str, object]] = {}
        for it in ranked:
            fp = str(it.get("file_path") or "")
            if not fp:
                continue
            prev = best_by_file.get(fp)
            if prev is None or cls._rank_key(it) < cls._rank_key(prev):
                best_by_file[fp] = it
        unique = sorted(best_by_file.values(), key=cls._rank_key)
        return cls._apply_precision_trim(unique, top_k)

    @classmethod
    async def _search_codegraph_files(
        cls,
        repo_id: str,
        keywords: List[str],
        *,
        top_k: int,
    ) -> List[Dict[str, object]]:
        if not settings.code_graph_enabled:
            return []
        from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway

        items: List[Dict[str, object]] = []
        try:
            with CodeGraphGateway.create_search() as q:
                for kw in keywords:
                    for method_name, hit_key in (
                        ("query_callers_of_symbol", "callers"),
                        ("query_callees_of_symbol", "callees"),
                    ):
                        method = getattr(q, method_name, None)
                        if method is None:
                            continue
                        res = await method(repo_id, kw, limit=top_k)
                        if not res.result:
                            continue
                        content = res.content or {}
                        for hit in content.get(hit_key) or []:
                            fp = str(hit.get("file_path") or "").replace("\\", "/")
                            if not fp:
                                continue
                            items.append(
                                {
                                    "file_path": fp,
                                    "symbol_kind": hit.get("kind"),
                                    "symbol_name": hit.get("name") or kw,
                                    "start_line": hit.get("start_line"),
                                    "end_line": hit.get("end_line"),
                                    "score": cls.CODEGRAPH_SCORE,
                                    "match_source": "codegraph",
                                    "exact_tier": None,
                                }
                            )
        except Exception as e:
            logging.warning("related CodeGraph 通道失败 repo_id=%s error=%s", repo_id, e)
        return items

    @staticmethod
    def related_channel_flags() -> Dict[str, bool]:
        """related 仅 symbol + codegraph（与能力 ENV 同源）。"""
        return {
            "symbol": bool(settings.code_analysis_symbol_summary_enabled),
            "codegraph": bool(settings.code_graph_enabled),
        }

    @staticmethod
    def capability_flags() -> Dict[str, bool]:
        return {
            "chunk": bool(settings.code_analysis_line_chunk_enabled),
            "symbol": bool(settings.code_analysis_symbol_summary_enabled),
            "codegraph": bool(settings.code_graph_enabled),
            "mr_experience": bool(settings.mr_experience_enabled),
        }

    @staticmethod
    async def search_similar_code(
        repo_id: str,
        code_text: str,
        top_k: int = 10,
    ) -> Dict[str, object]:
        if not settings.code_analysis_line_chunk_enabled:
            raise ValueError(
                "行块能力已关闭：请设置 CODE_ANALYSIS_LINE_CHUNK_ENABLED=true"
            )
        query = (code_text or "").strip()
        if not query:
            raise ValueError("code_text 不能为空")

        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")

        embed_queries = SimilarQueryNormalizer.build_embed_queries(query)
        fetch_k = max(top_k * SearchService.SIMILAR_FETCH_MULTIPLIER, SearchService.SIMILAR_MIN_FETCH)
        doc_batches: List[List[Dict[str, object]]] = []
        for q in embed_queries:
            docs = await CodeVectorSearchService.search_code_chunk_vectors(repo_id, [q], fetch_k)
            if docs:
                doc_batches.append(docs)
        merged_docs = SearchService._merge_similar_docs(doc_batches)
        unique = SearchService.fuse_similar_items(
            merged_docs,
            query_text=query,
            top_k=top_k,
        )
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "total": len(unique),
            "index": index,
            "items": unique,
        }

    @classmethod
    async def search_related_files(
        cls,
        repo_id: str,
        keywords: List[str],
        top_k: int = 10,
    ) -> Dict[str, object]:
        keywords = [str(k).strip() for k in (keywords or []) if k and str(k).strip()]
        if not keywords:
            raise ValueError("keywords 不能为空")

        channels = cls.related_channel_flags()
        if not any(channels.values()):
            raise ValueError(
                "related 能力全部关闭：请至少开启 CODE_ANALYSIS_SYMBOL_SUMMARY_ENABLED / "
                "CODE_GRAPH_ENABLED 之一"
            )

        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")

        fetch_k = max(top_k * 2, top_k)
        exact_items: List[Dict[str, object]] = []
        symbol_docs: List[Dict[str, object]] = []
        extra_items: List[Dict[str, object]] = []

        if channels["symbol"]:
            exact_items.extend(await ExactMatchService.match_symbols(repo_id, keywords, top_k=fetch_k))
            exact_items.extend(await ExactMatchService.match_paths(repo_id, keywords, top_k=fetch_k))
            symbol_docs = await CodeVectorSearchService.search_code_symbol_summary_vectors(
                repo_id, keywords, fetch_k
            )
        if channels["codegraph"]:
            extra_items.extend(
                await cls._search_codegraph_files(repo_id, keywords, top_k=fetch_k)
            )

        unique = cls.fuse_related_items(
            exact_items=exact_items,
            symbol_docs=symbol_docs,
            top_k=top_k,
            extra_items=extra_items,
        )
        for it in unique:
            it.pop("_raw_score", None)
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "keywords": keywords,
            "channels": channels,
            "total": len(unique),
            "index": index,
            "items": unique,
        }

    @staticmethod
    async def search_chunks(
        repo_id: str,
        query: str,
        top_k: int = 10,
    ) -> Dict[str, object]:
        """仅行块向量检索（人工调试用）。"""
        if not settings.code_analysis_line_chunk_enabled:
            raise ValueError(
                "行块能力已关闭：请设置 CODE_ANALYSIS_LINE_CHUNK_ENABLED=true"
            )
        q = (query or "").strip()
        if not q:
            raise ValueError("query 不能为空")
        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")
            kind = getattr(repo, "kind", None) or RepoKind.CODE
            if kind != RepoKind.CODE:
                raise ValueError(f"search chunks 仅支持 kind=code，当前 kind={kind}")

        docs = await CodeVectorSearchService.search_code_chunk_vectors(repo_id, [q], top_k)
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "query": q,
            "total": len(docs),
            "index": index,
            "items": [
                {
                    "file_path": doc.get("file_path"),
                    "start_line": doc.get("start_line"),
                    "end_line": doc.get("end_line"),
                    "content_preview": str(doc.get("content") or "")[:200],
                    "score": doc.get("_score"),
                    "match_source": "line_chunk",
                }
                for doc in docs
            ],
        }

    @staticmethod
    async def search_symbols(
        repo_id: str,
        query: str,
        top_k: int = 10,
    ) -> Dict[str, object]:
        """仅符号摘要向量检索（人工调试用）。"""
        if not settings.code_analysis_symbol_summary_enabled:
            raise ValueError(
                "符号能力已关闭：请设置 CODE_ANALYSIS_SYMBOL_SUMMARY_ENABLED=true"
            )
        q = (query or "").strip()
        if not q:
            raise ValueError("query 不能为空")
        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")
            kind = getattr(repo, "kind", None) or RepoKind.CODE
            if kind != RepoKind.CODE:
                raise ValueError(f"search symbols 仅支持 kind=code，当前 kind={kind}")

        docs = await CodeVectorSearchService.search_code_symbol_summary_vectors(repo_id, [q], top_k)
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "query": q,
            "total": len(docs),
            "index": index,
            "items": [
                {
                    "file_path": doc.get("file_path"),
                    "symbol_kind": doc.get("symbol_kind"),
                    "symbol_name": doc.get("symbol_name"),
                    "start_line": doc.get("start_line"),
                    "end_line": doc.get("end_line"),
                    "summary": doc.get("summary"),
                    "score": doc.get("_score"),
                    "match_source": "symbol_summary",
                }
                for doc in docs
            ],
        }

    @staticmethod
    async def search_patterns(
        repo_id: str,
        query: str,
        top_k: int = 10,
    ) -> Dict[str, object]:
        if not settings.mr_experience_enabled:
            raise ValueError("MR 经验能力已关闭：请设置 MR_EXPERIENCE_ENABLED=true")
        q = (query or "").strip()
        if not q:
            raise ValueError("query 不能为空")

        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")
            kind = getattr(repo, "kind", None) or RepoKind.CODE
            if kind != RepoKind.CODE:
                raise ValueError(f"search pattern 仅支持 kind=code，当前 kind={kind}")

        if not await PatternVectorService.space_exists(repo_id):
            raise ValueError("该仓库尚无经验数据，请先执行 experience analyze")

        items = await PatternVectorService.search(repo_id, q, top_k)
        min_score = float(settings.mr_experience_min_quality_score or 0.0)
        items = [it for it in items if float(it.get("quality_score") or 0.0) >= min_score]
        if settings.mr_experience_merge_by_scenario:
            items = PatternVectorService.merge_by_scenario(items)
        items = items[: max(1, top_k)]
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "query": q,
            "total": len(items),
            "index": index,
            "items": items,
        }
