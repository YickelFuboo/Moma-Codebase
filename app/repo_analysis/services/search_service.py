from typing import Dict, List
from sqlalchemy import select
from app.repo_mgmt.models.git_repo_mgmt import GitRepository
from app.repo_analysis.services.codevector.vector_search import CodeVectorSearchService
from app.infrastructure.database import get_db_session


class SearchService:
    """仓库内代码相似检索、关键词关联位置检索（向量库：行块 / 符号摘要）。"""

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
        return {
            "repo_id": repo_id,
            "total": len(docs),
            "items": [
                {
                    "file_path": doc.get("file_path"),
                    "start_line": doc.get("start_line"),
                    "end_line": doc.get("end_line"),
                }
                for doc in docs
            ],
        }

    @staticmethod
    async def search_related_files(
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

        docs = await CodeVectorSearchService.search_code_symbol_summary_vectors(repo_id, keywords, top_k)
        items1 = [
            {
                "file_path": doc.get("file_path"),
                "symbol_kind": doc.get("symbol_kind"),
                "symbol_name": doc.get("symbol_name"),
                "start_line": doc.get("start_line"),
                "end_line": doc.get("end_line"),
            }
            for doc in docs
        ]

        docs = await CodeVectorSearchService.search_code_chunk_vectors(repo_id, keywords, top_k)
        items2 = [
            {
                "file_path": doc.get("file_path"),
                "symbol_kind": doc.get("symbol_kind"),
                "symbol_name": doc.get("symbol_name"),
                "start_line": doc.get("start_line"),
                "end_line": doc.get("end_line"),
            }
            for doc in docs
        ]

        items = items1 + items2
        seen: set[tuple[object, object, object, object, object]] = set()
        unique: List[Dict[str, object]] = []
        for it in items:
            key = (
                it.get("file_path"),
                it.get("symbol_kind"),
                it.get("symbol_name"),
                it.get("start_line"),
                it.get("end_line"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(it)

        return {
            "repo_id": repo_id,
            "keywords": keywords,
            "total": len(unique),
            "items": unique,
        }
