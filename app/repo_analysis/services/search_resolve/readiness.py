from __future__ import annotations
from typing import Any, Dict
from app.repo_analysis.services.analysis_service import AnalysisService
from app.repo_analysis.services.search_resolve.errors import ResolveIndexNotReady


class ResolveReadiness:
    """resolve 前只读就绪检查：无可搜索文件时阻断，避免空结果被当成「没找到」。"""

    @classmethod
    async def ensure_searchable(cls, repo_id: str) -> Dict[str, Any]:
        summary = await AnalysisService.get_summary(repo_id)
        analysis = summary.get("analysis_summary") or {}
        searchable = bool(analysis.get("searchable"))
        searchable_files = int(analysis.get("searchable_files") or 0)
        if searchable and searchable_files > 0:
            return summary

        scan = summary.get("scan") or {}
        scan_status = scan.get("scan_status")
        stale_hint = summary.get("stale_hint")
        status_message = summary.get("status_message")
        hint = (
            "请先执行: mcb setup --path <仓> 或 mcb analyze --path <仓>；"
            "可用 mcb analyze status --path <仓> 查看进度。"
        )
        if scan_status == "running" or analysis.get("scan_active_in_process"):
            message = "索引仍在构建中，尚无可搜索文件"
        elif stale_hint and "never_scanned" in str(stale_hint):
            message = "仓库尚未完成分析，尚无可搜索文件"
        else:
            message = "索引未就绪：无可搜索文件"
        raise ResolveIndexNotReady(
            message,
            details={
                "repo_id": repo_id,
                "searchable_files": searchable_files,
                "scan_status": scan_status,
                "stale_hint": stale_hint,
                "status_message": status_message,
                "hint": hint,
            },
        )
