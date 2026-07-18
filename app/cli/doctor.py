from __future__ import annotations
import os
import sys
from typing import Any, Dict, List
import click
from sqlalchemy import func, select
from app.cli.common import echo_json, run_async
from app.cli.schemes import ExitCode
from app.config.settings import APP_NAME, APP_VERSION, settings
from app.infrastructure.database import get_db_session
from app.infrastructure.database.factory import health_check_db
from app.repo_mgmt.models.git_repo_mgmt import GitRepository
from app.repo_mgmt.services.repo_resolver import RepoResolver


class DoctorService:
    """环境自检：供 Agent / 人工确认 mcb 是否可对接。"""

    @classmethod
    async def run(cls) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        checks.append(cls._check_runtime_dir())
        checks.append(await cls._check_database())
        checks.append(cls._check_vector_store())
        checks.append(cls._check_codegraph())
        checks.append(await cls._check_repos())
        ok = all(c.get("ok") for c in checks)
        return {
            "ok": ok,
            "app": APP_NAME,
            "version": APP_VERSION,
            "checks": checks,
        }

    @staticmethod
    def _check_runtime_dir() -> Dict[str, Any]:
        path = os.path.abspath(settings.runtime_data_dir)
        exists = os.path.isdir(path)
        writable = False
        if exists:
            try:
                probe = os.path.join(path, ".mcb_doctor_write_probe")
                with open(probe, "w", encoding="utf-8") as f:
                    f.write("ok")
                os.remove(probe)
                writable = True
            except OSError:
                writable = False
        return {
            "name": "runtime_data_dir",
            "ok": exists and writable,
            "path": path,
            "exists": exists,
            "writable": writable,
        }

    @staticmethod
    async def _check_database() -> Dict[str, Any]:
        try:
            healthy = await health_check_db()
            return {
                "name": "database",
                "ok": bool(healthy),
                "engine": settings.database_type,
                "message": None if healthy else "health_check 失败",
            }
        except Exception as exc:
            return {
                "name": "database",
                "ok": False,
                "engine": settings.database_type,
                "message": str(exc),
            }

    @staticmethod
    def _check_vector_store() -> Dict[str, Any]:
        engine = (settings.vector_store_engine or "").lower()
        detail: Dict[str, Any] = {
            "name": "vector_store",
            "engine": engine,
        }
        try:
            if engine == "lancedb":
                uri = settings.resolved_lancedb_uri
                detail["uri"] = uri
                os.makedirs(uri, exist_ok=True)
                detail["ok"] = os.path.isdir(uri)
            else:
                from app.infrastructure.vector_store import get_vector_store_conn

                conn = get_vector_store_conn()
                detail["ok"] = conn is not None
            return detail
        except Exception as exc:
            detail["ok"] = False
            detail["message"] = str(exc)
            return detail

    @staticmethod
    def _check_codegraph() -> Dict[str, Any]:
        provider = (settings.code_graph_provider or "codegraph").lower()
        enabled = bool(settings.code_graph_enabled)
        row: Dict[str, Any] = {
            "name": "codegraph",
            "enabled": enabled,
            "provider": provider,
        }
        if not enabled:
            row["ok"] = True
            row["message"] = "已关闭（CODE_GRAPH_ENABLED=false）"
            return row
        if provider != "codegraph":
            row["ok"] = True
            row["message"] = f"provider={provider}，跳过 CLI 检测"
            return row
        try:
            from app.repo_analysis.services.codegraph.providers.codegraph.cli_runner import (
                CodeGraphCliRunner,
            )

            cli = CodeGraphCliRunner.find_cli()
            row["cli"] = cli
            row["ok"] = bool(cli)
            if not cli:
                row["message"] = "未找到 codegraph CLI（交互模式启动时会尝试安装）"
            return row
        except Exception as exc:
            row["ok"] = False
            row["message"] = str(exc)
            return row

    @staticmethod
    async def _check_repos() -> Dict[str, Any]:
        try:
            async with get_db_session() as db:
                total = await db.scalar(select(func.count()).select_from(GitRepository))
                result = await db.execute(select(GitRepository).limit(20))
                repos = result.scalars().all()
            samples = []
            for repo in repos:
                path = (
                    RepoResolver.normalize_repo_path(repo.local_path)
                    if repo.local_path
                    else None
                )
                samples.append(
                    {
                        "name": repo.repository_name,
                        "kind": getattr(repo, "kind", None) or "code",
                        "path": path,
                        "path_exists": bool(path and os.path.isdir(path)),
                    }
                )
            return {
                "name": "registered_repos",
                "ok": True,
                "total": int(total or 0),
                "samples": samples,
            }
        except Exception as exc:
            return {
                "name": "registered_repos",
                "ok": False,
                "message": str(exc),
            }


@click.command("doctor")
def doctor() -> None:
    """环境自检（JSON）：runtime / DB / 向量库 / CodeGraph / 已登记仓。"""

    async def _run():
        return await DoctorService.run()

    result = run_async(_run)
    echo_json(result)
    if not result.get("ok"):
        sys.exit(ExitCode.BUSINESS)
