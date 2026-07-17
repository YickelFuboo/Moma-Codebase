from __future__ import annotations
from typing import Dict, List, Tuple
from sqlalchemy import select
from app.infrastructure.database import get_db_session
from app.repo_analysis.services.codevector.exact_match import ExactMatchService
from app.repo_analysis.services.codevector.vector_search import CodeVectorSearchService
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService
from app.repo_analysis.services.search_index_meta import SearchIndexMeta
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


class SearchService:
    """仓库内代码相似检索、关键词关联位置检索、历史经验模式检索。"""

    EXACT_SYMBOL_BOOST = 1.2
    EXACT_PATH_BOOST = 0.3

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
    def _rank_key(cls, item: Dict[str, object]) -> Tuple[int, float, str]:
        source = str(item.get("match_source") or "")
        tier = str(item.get("exact_tier") or "")
        score = float(item.get("score") or 0)
        if source == "exact" and tier == "symbol":
            group = 0
        elif source == "exact":
            group = 1
        else:
            group = 2
        return (group, -score, str(item.get("file_path") or ""))

    @classmethod
    def fuse_related_items(
        cls,
        *,
        exact_items: List[Dict[str, object]],
        symbol_docs: List[Dict[str, object]],
        chunk_docs: List[Dict[str, object]],
        top_k: int,
    ) -> List[Dict[str, object]]:
        """精确符号 > 精确路径 > 向量；按 file_path 保留最高分一条再截断。"""
        ranked: List[Dict[str, object]] = []
        for it in exact_items:
            raw = float(it.get("_score") or 0)
            tier = str(it.get("exact_tier") or ("symbol" if raw >= 1.8 else "path"))
            boost = cls.EXACT_SYMBOL_BOOST if tier == "symbol" else cls.EXACT_PATH_BOOST
            ranked.append(
                {
                    "file_path": it.get("file_path"),
                    "symbol_kind": it.get("symbol_kind"),
                    "symbol_name": it.get("symbol_name"),
                    "start_line": it.get("start_line"),
                    "end_line": it.get("end_line"),
                    "score": raw + boost,
                    "match_source": "exact",
                    "exact_tier": tier,
                }
            )
        for doc in symbol_docs:
            ranked.append(cls._normalize_vector_item(doc, "symbol_summary"))
        for doc in chunk_docs:
            ranked.append(cls._normalize_vector_item(doc, "line_chunk"))

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
        return unique[: max(1, top_k)]

    @staticmethod
    async def search_similar_code(
        repo_id: str,
        code_text: str,
        top_k: int = 10,
    ) -> Dict[str, object]:
        query = (code_text or "").strip()
        if not query:
            raise ValueError("code_text 不能为空")

        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")

        docs = await CodeVectorSearchService.search_code_chunk_vectors(repo_id, [query], top_k)
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "total": len(docs),
            "index": index,
            "items": [
                {
                    "file_path": doc.get("file_path"),
                    "start_line": doc.get("start_line"),
                    "end_line": doc.get("end_line"),
                    "score": doc.get("_score"),
                    "match_source": "line_chunk",
                }
                for doc in docs
            ],
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

        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")

        fetch_k = max(top_k * 2, top_k)
        exact_sym = await ExactMatchService.match_symbols(repo_id, keywords, top_k=fetch_k)
        exact_path = await ExactMatchService.match_chunk_paths(repo_id, keywords, top_k=fetch_k)
        symbol_docs = await CodeVectorSearchService.search_code_symbol_summary_vectors(
            repo_id, keywords, fetch_k
        )
        chunk_docs = await CodeVectorSearchService.search_code_chunk_vectors(
            repo_id, keywords, fetch_k
        )
        unique = cls.fuse_related_items(
            exact_items=exact_sym + exact_path,
            symbol_docs=symbol_docs,
            chunk_docs=chunk_docs,
            top_k=top_k,
        )
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "keywords": keywords,
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
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "query": q,
            "total": len(items),
            "index": index,
            "items": items,
        }
