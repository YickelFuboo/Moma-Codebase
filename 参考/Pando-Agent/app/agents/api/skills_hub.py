"""Skills Hub HTTP API（全局技能市场安装）。"""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from ..skills.hub import HUB_SERVICE
from ..skills.manager import SkillsManager
from ..skills.remarks import set_skill_remark
from ..skills.paths import find_skill
from ..contants import BUILTIN_SKILLS_DIR

router = APIRouter()


class HubRemarkRequest(BaseModel):
    remark: str = Field(default="", description="用户备注，写入 data/skills/.remarks.json")


class HubInstallRequest(BaseModel):
    identifier: str = Field(..., description="技能标识，如 builtin:cron 或 github:openai/skills/pdf")
    force: bool = Field(default=False, description="社区源非 dangerous 时强制安装")
    enable_for_agents: list[str] = Field(
        default_factory=list,
        description="安装成功后自动在指定 Agent 的 config.json 中启用该 Skill",
    )


@router.get("/hub/search", summary="搜索可安装 Skill")
async def hub_search(
    q: str = Query(default="", description="关键词或 github:owner/repo；留空浏览该来源全部 Skill"),
    source: str = Query(
        default="all",
        description="all | builtin | github | clawhub | skills-sh | well-known | lobehub（bundled 为兼容别名）",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    try:
        return await HUB_SERVICE.search(q, source=source, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"skills hub search failed: {e}") from e


@router.get("/hub/inspect", summary="预览 Skill 元数据")
async def hub_inspect(
    identifier: str = Query(..., description="如 builtin:cron 或 github:openai/skills/pdf"),
    include_content: bool = Query(default=False, description="是否附带 SKILL.md 正文预览"),
) -> Dict[str, Any]:
    try:
        return await HUB_SERVICE.inspect(identifier, include_content=include_content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"skills hub inspect failed: {e}") from e


@router.post("/hub/install", summary="安装 Skill 到全局 skills 目录（RUNTIME_DATA_DIR/skills）")
async def hub_install(body: HubInstallRequest) -> Dict[str, Any]:
    try:
        return await HUB_SERVICE.install(
            body.identifier,
            force=body.force,
            enable_for_agents=body.enable_for_agents,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"skills hub install failed: {e}") from e


@router.get("/hub/installed", summary="列出 Hub 已安装 Skill")
async def hub_installed() -> Dict[str, Any]:
    items = HUB_SERVICE.list_installed()
    return {"count": len(items), "skills": items}


@router.put("/hub/remarks/{skill_name}", summary="更新 Skill 用户备注（data/skills/.remarks.json）")
async def hub_set_remark(skill_name: str, body: HubRemarkRequest) -> Dict[str, Any]:
    try:
        key = SkillsManager.validate_skill_name(skill_name)
        if not find_skill(BUILTIN_SKILLS_DIR, key):
            raise ValueError(f"Skill 不存在于 data/skills: {key}")
        return {"skill": set_skill_remark(key, body.remark)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/hub/preinstalled", summary="列出系统自带 Skill（data/skills 中未经 Hub 安装的项）")
async def hub_preinstalled() -> Dict[str, Any]:
    return HUB_SERVICE.list_preinstalled()


@router.delete("/hub/installed/{skill_name}", summary="卸载 Hub 管理的 Skill")
async def hub_uninstall(skill_name: str) -> Dict[str, Any]:
    try:
        return HUB_SERVICE.uninstall(skill_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/hub/check", summary="检查 Hub 已安装 Skill 是否有上游更新")
async def hub_check(
    name: str = Query(default="", description="可选：仅检查指定 skill 名"),
) -> Dict[str, Any]:
    try:
        items = await HUB_SERVICE.check_updates(name.strip() or None)
        updates = [x for x in items if x.get("update_available")]
        return {"count": len(items), "updates_available": len(updates), "skills": items}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"skills hub check failed: {e}") from e


class HubUpdateRequest(BaseModel):
    name: str = Field(..., description="Hub 已安装的 skill 名")
    force: bool = Field(default=False, description="社区源非 dangerous 时强制更新")


@router.post("/hub/update", summary="更新 Hub 已安装 Skill")
async def hub_update(body: HubUpdateRequest) -> Dict[str, Any]:
    try:
        return await HUB_SERVICE.update(body.name, force=body.force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"skills hub update failed: {e}") from e


@router.post("/hub/audit", summary="对 Hub 已安装 Skill 重新安全扫描")
async def hub_audit(
    name: str = Query(default="", description="可选：仅审计指定 skill 名"),
) -> Dict[str, Any]:
    try:
        items = HUB_SERVICE.audit(name.strip() or None)
        return {"count": len(items), "skills": items}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class HubEnableAgentsRequest(BaseModel):
    name: str = Field(..., description="Skill 目录名")
    agent_types: list[str] = Field(..., description="要启用的 Agent 类型列表")
    sync: bool = Field(
        default=False,
        description="为 true 时按 agent_types 同步勾选状态（未勾选将从 permissions 移除允许）",
    )


@router.post("/hub/enable-agents", summary="在指定 Agent 配置中启用或同步 Skill")
async def hub_enable_agents(body: HubEnableAgentsRequest) -> Dict[str, Any]:
    try:
        if body.sync:
            items = HUB_SERVICE.sync_for_agents(body.name, body.agent_types)
            changed = [x for x in items if x.get("status") in ("enabled", "disabled")]
            return {"count": len(items), "changed": len(changed), "agents": items}
        items = HUB_SERVICE.enable_for_agents(body.name, body.agent_types)
        enabled = [x for x in items if x.get("status") == "enabled"]
        return {"count": len(items), "enabled": len(enabled), "agents": items}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/hub/audit-log", summary="读取 Hub 审计日志（最近条目）")
async def hub_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
) -> Dict[str, Any]:
    lines = HUB_SERVICE.list_audit_log(limit=limit)
    return {"count": len(lines), "lines": lines}


@router.get("/hub/taps", summary="列出 GitHub tap（内置 + 自定义）")
async def hub_list_taps() -> Dict[str, Any]:
    return HUB_SERVICE.list_github_taps()


class HubTapRequest(BaseModel):
    repo: str = Field(..., description="GitHub 仓库，格式 owner/repo")


@router.post("/hub/taps", summary="添加自定义 GitHub tap")
async def hub_add_tap(body: HubTapRequest) -> Dict[str, Any]:
    try:
        return HUB_SERVICE.add_github_tap(body.repo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/hub/taps", summary="移除自定义 GitHub tap")
async def hub_remove_tap(
    repo: str = Query(..., description="owner/repo"),
) -> Dict[str, Any]:
    try:
        return HUB_SERVICE.remove_github_tap(repo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/hub/wellknown-hosts", summary="列出 well-known 注册域名")
async def hub_list_wellknown_hosts() -> Dict[str, Any]:
    return HUB_SERVICE.list_wellknown_hosts()


class HubWellKnownHostRequest(BaseModel):
    host: str = Field(..., description="域名，如 docs.example.com")


@router.post("/hub/wellknown-hosts", summary="添加自定义 well-known 域名")
async def hub_add_wellknown_host(body: HubWellKnownHostRequest) -> Dict[str, Any]:
    try:
        return HUB_SERVICE.add_wellknown_host(body.host)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/hub/wellknown-hosts", summary="移除自定义 well-known 域名")
async def hub_remove_wellknown_host(
    host: str = Query(..., description="域名"),
) -> Dict[str, Any]:
    try:
        return HUB_SERVICE.remove_wellknown_host(host)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
