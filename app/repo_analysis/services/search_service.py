from typing import Dict, List
from sqlalchemy import select
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind
from app.repo_analysis.services.codevector.vector_search import CodeVectorSearchService
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService
from app.infrastructure.database import get_db_session


class SearchService:
    """仓库内代码相似检索、关键词关联位置检索、历史经验模式检索。"""

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
        return {
            "repo_id": repo_id,
            "query": q,
            "total": len(items),
            "items": items,
        }
