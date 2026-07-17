from __future__ import annotations
import asyncio
import logging
from typing import Dict, List, Optional
from sqlalchemy import select
from app.config.settings import settings
from app.infrastructure.database import get_db_session
from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
from app.repo_analysis.services.search_index_meta import SearchIndexMeta
from app.repo_analysis.services.search_resolve.intent import ResolvePlan, SearchIntentRouter
from app.repo_analysis.services.search_service import SearchService
from app.repo_mgmt.models.git_repo_mgmt import GitRepository, RepoKind


class SearchResolveService:
    """统一检索编排：规则路由 + 多通道并行 + 带来源融合结果。"""

    CHANNEL_PRIORITY = {
        "exact": 0,
        "symbol_summary": 1,
        "codegraph": 2,
        "line_chunk": 3,
        "mr_experience": 4,
        "api": 5,
        "graph": 2,
    }

    @classmethod
    async def resolve(
        cls,
        repo_id: str,
        query: str,
        *,
        top_k: int = 10,
        intent: Optional[str] = None,
    ) -> Dict[str, object]:
        async with get_db_session() as db:
            repo = await db.scalar(select(GitRepository).where(GitRepository.id == repo_id))
            if not repo:
                raise ValueError("仓库不存在")
            kind = getattr(repo, "kind", None) or RepoKind.CODE

        plan = SearchIntentRouter.plan(query, repo_kind=kind, intent_override=intent)
        sections: Dict[str, object] = {}
        channel_errors: Dict[str, str] = {}
        fused_items: List[Dict[str, object]] = []

        tasks = []
        for channel in plan.channels:
            tasks.append(cls._run_channel(repo_id, channel, plan, top_k=top_k))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for channel, result in zip(plan.channels, results):
            if isinstance(result, Exception):
                channel_errors[channel] = str(result)
                logging.warning(
                    "resolve 通道失败 repo_id=%s channel=%s error=%s",
                    repo_id,
                    channel,
                    result,
                )
                sections[channel] = {"total": 0, "items": [], "error": str(result)}
                continue
            sections[channel] = result
            for item in result.get("items") or []:
                fused = dict(item)
                fused.setdefault("channel", channel)
                if channel == "pattern":
                    fused.setdefault("match_source", "mr_experience")
                elif channel == "api":
                    fused.setdefault("match_source", "api")
                elif channel == "graph":
                    fused.setdefault("match_source", "codegraph")
                fused_items.append(fused)

        fused_items = cls._fuse_items(fused_items, top_k=top_k)
        index = await SearchIndexMeta.for_repo(repo_id)
        return {
            "repo_id": repo_id,
            "query": query,
            "intent": plan.intent.value,
            "intent_reason": plan.reason,
            "fallback_from": plan.fallback_from,
            "channels_used": [c for c in plan.channels if c not in channel_errors],
            "channel_errors": channel_errors or None,
            "plan": {
                "channels": plan.channels,
                "keywords": plan.keywords,
                "graph_file": plan.graph_file,
                "graph_symbol": plan.graph_symbol,
                "graph_mode": plan.graph_mode,
            },
            "total": len(fused_items),
            "index": index,
            "items": fused_items,
            "sections": sections,
        }

    @classmethod
    async def _run_channel(
        cls,
        repo_id: str,
        channel: str,
        plan: ResolvePlan,
        *,
        top_k: int,
    ) -> Dict[str, object]:
        if channel == "similar":
            if not settings.code_analysis_line_chunk_enabled:
                raise ValueError("行块能力已关闭")
            result = await SearchService.search_similar_code(repo_id, plan.code_text, top_k=top_k)
            return {"total": result.get("total"), "items": result.get("items") or []}

        if channel == "related":
            keywords = plan.keywords or [plan.code_text]
            result = await SearchService.search_related_files(repo_id, keywords, top_k=top_k)
            return {"total": result.get("total"), "items": result.get("items") or []}

        if channel == "pattern":
            if not settings.mr_experience_enabled:
                raise ValueError("MR 经验能力已关闭")
            result = await SearchService.search_patterns(repo_id, plan.code_text, top_k=top_k)
            items = []
            for it in result.get("items") or []:
                row = dict(it)
                row.setdefault("match_source", "mr_experience")
                items.append(row)
            return {"total": len(items), "items": items}

        if channel == "api":
            from app.lib_analysis.services.search_service import LibSearchService

            result = await LibSearchService.search_apis(repo_id, plan.code_text, top_k=top_k)
            items = []
            for it in result.get("items") or []:
                row = dict(it)
                row["match_source"] = "api"
                row["symbol_name"] = row.get("api_name")
                row["symbol_kind"] = row.get("api_kind")
                items.append(row)
            return {"total": len(items), "items": items}

        if channel == "graph":
            return await cls._run_graph_channel(repo_id, plan, top_k=top_k)

        raise ValueError(f"未知通道: {channel}")

    @classmethod
    async def _run_graph_channel(
        cls,
        repo_id: str,
        plan: ResolvePlan,
        *,
        top_k: int,
    ) -> Dict[str, object]:
        if not settings.code_graph_enabled:
            raise ValueError("CodeGraph 能力已关闭")
        items: List[Dict[str, object]] = []
        mode = plan.graph_mode or "dependents"
        with CodeGraphGateway.create_search() as q:
            if mode == "dependents" and plan.graph_file:
                res = await q.query_dependents_of_file(repo_id, plan.graph_file)
                if not res.result:
                    raise ValueError(res.message or "dependents 查询失败")
                for fp in (res.content or {}).get("dependents") or []:
                    items.append(
                        {
                            "file_path": str(fp).replace("\\", "/"),
                            "score": SearchService.CODEGRAPH_SCORE,
                            "match_source": "codegraph",
                            "graph_relation": "dependents",
                            "graph_target": plan.graph_file,
                        }
                    )
            elif mode == "dependencies" and plan.graph_file:
                res = await q.query_dependented_of_file(repo_id, plan.graph_file)
                if not res.result:
                    raise ValueError(res.message or "dependencies 查询失败")
                for fp in (res.content or {}).get("dependented") or []:
                    items.append(
                        {
                            "file_path": str(fp).replace("\\", "/"),
                            "score": SearchService.CODEGRAPH_SCORE,
                            "match_source": "codegraph",
                            "graph_relation": "dependencies",
                            "graph_target": plan.graph_file,
                        }
                    )
            elif mode == "callers" and plan.graph_symbol:
                res = await q.query_callers_of_symbol(repo_id, plan.graph_symbol, limit=top_k)
                if not res.result:
                    raise ValueError(res.message or "callers 查询失败")
                for hit in (res.content or {}).get("callers") or []:
                    items.append(
                        {
                            "file_path": str(hit.get("file_path") or "").replace("\\", "/"),
                            "symbol_name": hit.get("name"),
                            "symbol_kind": hit.get("kind"),
                            "start_line": hit.get("start_line"),
                            "end_line": hit.get("end_line"),
                            "score": SearchService.CODEGRAPH_SCORE,
                            "match_source": "codegraph",
                            "graph_relation": "callers",
                            "graph_target": plan.graph_symbol,
                        }
                    )
            elif mode == "callees" and plan.graph_symbol:
                res = await q.query_callees_of_symbol(repo_id, plan.graph_symbol, limit=top_k)
                if not res.result:
                    raise ValueError(res.message or "callees 查询失败")
                for hit in (res.content or {}).get("callees") or []:
                    items.append(
                        {
                            "file_path": str(hit.get("file_path") or "").replace("\\", "/"),
                            "symbol_name": hit.get("name"),
                            "symbol_kind": hit.get("kind"),
                            "start_line": hit.get("start_line"),
                            "end_line": hit.get("end_line"),
                            "score": SearchService.CODEGRAPH_SCORE,
                            "match_source": "codegraph",
                            "graph_relation": "callees",
                            "graph_target": plan.graph_symbol,
                        }
                    )
            else:
                raise ValueError("graph 通道缺少有效 file/symbol")
        return {"total": len(items), "items": items[: max(1, top_k)]}

    @classmethod
    def _fuse_items(cls, items: List[Dict[str, object]], *, top_k: int) -> List[Dict[str, object]]:
        if not items:
            return []

        def _rank_key(it: Dict[str, object]) -> tuple:
            source = str(it.get("match_source") or "")
            channel = str(it.get("channel") or "")
            priority = cls.CHANNEL_PRIORITY.get(source, 9)
            if channel == "pattern" and source == "mr_experience":
                priority = 4
            score = float(it.get("score") or it.get("quality_score") or 0)
            return (priority, -score, str(it.get("file_path") or ""), str(it.get("title") or ""))

        best_by_key: Dict[str, Dict[str, object]] = {}
        for it in items:
            fp = str(it.get("file_path") or "")
            title = str(it.get("title") or "")
            key = fp or f"title:{title}" or str(it.get("symbol_name") or "")
            if not key:
                continue
            prev = best_by_key.get(key)
            if prev is None or _rank_key(it) < _rank_key(prev):
                best_by_key[key] = it
        unique = sorted(best_by_key.values(), key=_rank_key)
        return unique[: max(1, top_k)]
