from __future__ import annotations
import asyncio
import time
from typing import Any, Dict
import click
from app.cli.common import (
    DEFAULT_USER_ID,
    default_repo_name,
    echo_json,
    get_repo_by_path,
    repo_public_view,
    run_async,
)
from app.cli.doctor import DoctorService
from app.cli.schemes import ExitCode
from app.infrastructure.database import get_db_session
from app.repo_analysis.services.analysis_service import AnalysisService
from app.repo_mgmt.models.git_repo_mgmt import RepoKind
from app.repo_mgmt.services.git_repo_service import GitRepositoryService
from app.repo_mgmt.services.repo_resolver import RepoResolver


class SetupService:
    """一键就绪：登记 → doctor/模型探测 → analyze → 等到可检索。"""

    DEFAULT_WAIT_SEC = 600
    DEFAULT_POLL_MS = 2000

    @classmethod
    async def run(
        cls,
        path: str,
        *,
        kind: str = RepoKind.CODE,
        wait_sec: int = DEFAULT_WAIT_SEC,
        poll_ms: int = DEFAULT_POLL_MS,
        skip_analyze: bool = False,
    ) -> Dict[str, Any]:
        normalized = RepoResolver.normalize_repo_path(path)
        steps: list[Dict[str, Any]] = []

        doctor = await DoctorService.run()
        steps.append({"name": "doctor", "ok": bool(doctor.get("ok")), "result": doctor})
        if not doctor.get("ok"):
            return {
                "ok": False,
                "path": normalized,
                "steps": steps,
                "error": {
                    "code": "doctor_failed",
                    "message": "环境自检未通过，请先修复 doctor 失败项（含 embedding 探测）",
                    "hint": "poetry run mcb doctor",
                },
                "next": {"command": "poetry run mcb doctor"},
            }

        registered_new = False
        async with get_db_session() as db:
            existing = await RepoResolver.get_by_path(db, normalized)
            if existing:
                repo = existing
                steps.append(
                    {
                        "name": "repo_register",
                        "ok": True,
                        "already_registered": True,
                        "repo": repo_public_view(repo),
                    }
                )
            else:
                repo = await GitRepositoryService.create_repository_from_path(
                    session=db,
                    user_id=DEFAULT_USER_ID,
                    name=default_repo_name(normalized),
                    description="",
                    local_repo_path=normalized,
                    git_url="",
                    kind=kind.lower(),
                )
                registered_new = True
                steps.append(
                    {
                        "name": "repo_register",
                        "ok": True,
                        "already_registered": False,
                        "repo": repo_public_view(repo),
                    }
                )

        repo = await get_repo_by_path(normalized)
        repo_kind = getattr(repo, "kind", None) or RepoKind.CODE

        if skip_analyze:
            summary = await cls._summary_for(repo.id, repo_kind)
            searchable = bool((summary.get("analysis_summary") or {}).get("searchable"))
            return cls._result(
                ok=searchable,
                path=normalized,
                kind=repo_kind,
                steps=steps,
                summary=summary,
                registered_new=registered_new,
                analyze_started=False,
                waited_sec=0,
                message="已跳过 analyze；若不可检索请去掉 --skip-analyze 重跑",
            )

        start_info = await cls._start_analyze(repo.id, repo_kind)
        steps.append({"name": "analyze_start", "ok": True, "result": start_info})

        deadline = time.monotonic() + max(1, int(wait_sec))
        poll_sec = max(0.2, int(poll_ms) / 1000.0)
        summary: Dict[str, Any] = {}
        waited = 0.0
        t0 = time.monotonic()
        while True:
            summary = await cls._summary_for(repo.id, repo_kind)
            analysis = summary.get("analysis_summary") or {}
            if analysis.get("searchable"):
                waited = time.monotonic() - t0
                steps.append(
                    {
                        "name": "wait_searchable",
                        "ok": True,
                        "waited_sec": round(waited, 1),
                        "searchable_files": analysis.get("searchable_files"),
                    }
                )
                return cls._result(
                    ok=True,
                    path=normalized,
                    kind=repo_kind,
                    steps=steps,
                    summary=summary,
                    registered_new=registered_new,
                    analyze_started=True,
                    waited_sec=round(waited, 1),
                    message="索引已可检索",
                )
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(poll_sec)

        waited = time.monotonic() - t0
        steps.append(
            {
                "name": "wait_searchable",
                "ok": False,
                "waited_sec": round(waited, 1),
                "message": "等待可检索超时；分析可能仍在后台进行",
            }
        )
        return cls._result(
            ok=False,
            path=normalized,
            kind=repo_kind,
            steps=steps,
            summary=summary,
            registered_new=registered_new,
            analyze_started=True,
            waited_sec=round(waited, 1),
            message="等待可检索超时，请稍后 mcb analyze status 查看进度后重试 resolve",
        )

    @staticmethod
    async def _start_analyze(repo_id: str, kind: str) -> Dict[str, Any]:
        if kind == RepoKind.LIB:
            from app.lib_analysis.services.analysis_service import LibAnalysisService

            return await LibAnalysisService.start_scan(repo_id=repo_id)
        return await AnalysisService.start_scan(repo_id=repo_id)

    @staticmethod
    async def _summary_for(repo_id: str, kind: str) -> Dict[str, Any]:
        if kind == RepoKind.LIB:
            from app.lib_analysis.services.analysis_service import LibAnalysisService

            return await LibAnalysisService.get_summary(repo_id)
        return await AnalysisService.get_summary(repo_id)

    @classmethod
    def _result(
        cls,
        *,
        ok: bool,
        path: str,
        kind: str,
        steps: list,
        summary: Dict[str, Any],
        registered_new: bool,
        analyze_started: bool,
        waited_sec: float,
        message: str,
    ) -> Dict[str, Any]:
        resolve_example = (
            f'poetry run mcb search resolve --path {path} '
            f'--query "登录鉴权在哪实现" --timeout-ms 60000'
        )
        analysis = (summary or {}).get("analysis_summary") or {}
        return {
            "ok": ok,
            "path": path,
            "kind": kind,
            "registered_new": registered_new,
            "analyze_started": analyze_started,
            "waited_sec": waited_sec,
            "message": message,
            "status_message": (summary or {}).get("status_message"),
            "searchable": bool(analysis.get("searchable")),
            "searchable_files": analysis.get("searchable_files"),
            "stale_hint": (summary or {}).get("stale_hint"),
            "steps": steps,
            "next": {
                "command": resolve_example,
                "skill": "skills/mcb-resolve/SKILL.md",
                "note": "参考加速，非精确索引；改完代码若感觉飘，先看 analyze status / index 是否过期。",
            },
        }


@click.command("setup")
@click.option(
    "--path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="本地代码仓目录",
)
@click.option(
    "--kind",
    default=RepoKind.CODE,
    show_default=True,
    type=click.Choice(RepoKind.VALUES, case_sensitive=False),
    help="新登记时的仓库类型",
)
@click.option(
    "--wait-sec",
    default=SetupService.DEFAULT_WAIT_SEC,
    show_default=True,
    help="等待可检索的最长秒数",
)
@click.option(
    "--poll-ms",
    default=SetupService.DEFAULT_POLL_MS,
    show_default=True,
    help="轮询 analyze status 的间隔毫秒",
)
@click.option(
    "--skip-analyze",
    is_flag=True,
    default=False,
    help="只做登记与 doctor，不启动 analyze",
)
def setup(
    path: str,
    kind: str,
    wait_sec: int,
    poll_ms: int,
    skip_analyze: bool,
) -> None:
    """一键就绪：doctor → 登记 → analyze → 等到可检索，并打印 resolve 示例。"""

    async def _run() -> Dict[str, Any]:
        return await SetupService.run(
            path,
            kind=kind,
            wait_sec=wait_sec,
            poll_ms=poll_ms,
            skip_analyze=skip_analyze,
        )

    result = run_async(_run, scheduler=True)
    echo_json(result)
    if not result.get("ok"):
        raise SystemExit(ExitCode.BUSINESS)
