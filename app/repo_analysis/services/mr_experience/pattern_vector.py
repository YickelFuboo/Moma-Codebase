import hashlib
import json
import logging
from typing import Dict, List, Optional
from app.infrastructure.llms import embedding_factory
from app.infrastructure.vector_store import MatchDenseExpr, SearchRequest, VECTOR_STORE_CONN
from app.repo_analysis.constants.experience_space import ExperienceAnalysisType, mr_pattern_space_name
from app.repo_analysis.services.codevector.code_vector import CodeVectorService
from app.repo_analysis.services.mr_experience.models import ExperiencePattern


class PatternVectorService:
    """经验模式向量写入与检索（仅 ready 记录）。"""

    @staticmethod
    def build_embed_text(pattern: ExperiencePattern) -> str:
        steps = "；".join(f"{s.file}: {s.action}" for s in pattern.steps)
        return f"{pattern.title}\n{pattern.commit_message}\n{steps}".strip()

    @staticmethod
    async def upsert_pattern(repo_id: str, pattern: ExperiencePattern) -> None:
        text = PatternVectorService.build_embed_text(pattern)
        vectors = await CodeVectorService._embed_texts([text])
        if not vectors:
            raise RuntimeError("经验向量化失败")
        dim = len(vectors[0])
        vector_field = f"q_{dim}_vec"
        space = mr_pattern_space_name(repo_id, dim)
        await VECTOR_STORE_CONN.create_space(space, dim)
        sha = (pattern.source_commits or ["unknown"])[0]
        await VECTOR_STORE_CONN.delete_records(
            space,
            {
                "repo_id": repo_id,
                "analysis_type": ExperienceAnalysisType.MR_PATTERN_VECTOR,
                "symbol_name": sha,
            },
        )
        stable_id = hashlib.sha1(f"{repo_id}|mr_pattern|{sha}".encode("utf-8")).hexdigest()
        steps_payload = [{"file": s.file, "action": s.action} for s in pattern.steps]
        record = {
            "id": stable_id,
            "repo_id": repo_id,
            "file_path": "",
            "analysis_type": ExperienceAnalysisType.MR_PATTERN_VECTOR,
            "symbol_kind": "mr_pattern",
            "symbol_name": sha,
            "content": pattern.title,
            "summary": json.dumps(
                {
                    "title": pattern.title,
                    "steps": steps_payload,
                    "source_commits": pattern.source_commits,
                    "commit_message": pattern.commit_message,
                },
                ensure_ascii=False,
            ),
            "start_line": 0,
            "end_line": 0,
            vector_field: vectors[0],
        }
        failed = await VECTOR_STORE_CONN.insert_records(space, [record])
        if failed:
            raise RuntimeError(f"经验向量写入失败: {failed}")

    @staticmethod
    async def search(repo_id: str, query: str, top_k: int = 10) -> List[Dict[str, object]]:
        q = (query or "").strip()
        if not q:
            return []
        rows = await CodeVectorService._embed_texts([q])
        if not rows:
            return []
        dim = len(rows[0])
        space = mr_pattern_space_name(repo_id, dim)
        if not await VECTOR_STORE_CONN.space_exists(space):
            return []
        request = SearchRequest(
            select_fields=[
                "repo_id",
                "analysis_type",
                "symbol_name",
                "content",
                "summary",
            ],
            condition={
                "repo_id": repo_id,
                "analysis_type": ExperienceAnalysisType.MR_PATTERN_VECTOR,
            },
            match_exprs=[
                MatchDenseExpr(
                    vector_column_name=f"q_{dim}_vec",
                    embedding_data=rows[0],
                    embedding_data_type="float",
                    distance_type="cosine",
                    topn=top_k,
                )
            ],
            limit=top_k,
        )
        result = await VECTOR_STORE_CONN.search([space], request)
        docs = VECTOR_STORE_CONN.get_source(result) if result else []
        items: List[Dict[str, object]] = []
        for doc in docs:
            payload = PatternVectorService._parse_summary(doc.get("summary"))
            items.append(
                {
                    "title": payload.get("title") or doc.get("content"),
                    "similarity": doc.get("_score"),
                    "steps": payload.get("steps") or [],
                    "source_commits": payload.get("source_commits")
                    or ([doc.get("symbol_name")] if doc.get("symbol_name") else []),
                    "commit_message": payload.get("commit_message") or "",
                }
            )
        return items

    @staticmethod
    def _parse_summary(raw: object) -> dict:
        if isinstance(raw, dict):
            return raw
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    async def delete_repo_patterns(repo_id: str) -> int:
        model = embedding_factory.create_model()
        if not model:
            return 0
        vectors, _ = await model.encode(["x"])
        if vectors is None or len(vectors) == 0:
            return 0
        dim = len(vectors[0])
        space = mr_pattern_space_name(repo_id, dim)
        if not await VECTOR_STORE_CONN.space_exists(space):
            return 0
        deleted = int(await VECTOR_STORE_CONN.delete_records(space, {"repo_id": repo_id}))
        logging.info("已删除经验向量 repo_id=%s count=%s", repo_id, deleted)
        return deleted

    @staticmethod
    async def space_exists(repo_id: str) -> bool:
        model = embedding_factory.create_model()
        if not model:
            return False
        vectors, _ = await model.encode(["x"])
        if vectors is None or len(vectors) == 0:
            return False
        dim = len(vectors[0])
        return await VECTOR_STORE_CONN.space_exists(mr_pattern_space_name(repo_id, dim))
