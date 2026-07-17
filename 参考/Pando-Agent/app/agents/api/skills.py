"""Agent Skill 管理 API（设置页）。"""
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..skills.hub.lock import get_lock_entry, remove_lock_entry
from ..skills.hub.preinstalled import invalidate_preinstalled_cache
from ..skills.manager import SKILL_SOURCE_BUILTIN, SKILL_SOURCE_EXTERNAL, SkillsManager
from ..skills.remarks import get_skill_remark_entry, remove_skill_remark, set_skill_remark
from .common import (
    AgentConfigError,
    agent_dir,
    build_catalog,
    config_error_to_http,
    skills_manager_for_agent,
)


router = APIRouter()


class SkillCreateRequest(BaseModel):
    name: str = Field(..., description="Skill 目录名")
    description: str = Field(default="", description="frontmatter description")
    category: str = Field(default="general", description="安装目录 category（skills/<category>/<name>/）")
    content: Optional[str] = Field(default=None, description="SKILL.md 正文或完整文件；省略则自动生成模板")


class SkillFileUpdateRequest(BaseModel):
    content: str = Field(..., description="文件全文")
    file_path: str = Field(default="SKILL.md", description="技能目录内相对路径")


class SkillRemarkUpdateRequest(BaseModel):
    remark: str = Field(default="", description="用户备注，写入 data/skills/.remarks.json")


class SkillDetailResponse(BaseModel):
    name: str
    source: str
    editable: bool
    deletable: bool
    content: str
    description: str = ""
    category: str = "general"
    remark: str = ""
    remark_editable: bool = False
    remark_updated_at: str | None = None


@router.get(
    "/config/{agent_type}/skills/{skill_name}",
    summary="获取 Skill 详情（含 SKILL.md 全文）",
    response_model=SkillDetailResponse,
)
async def get_agent_skill(agent_type: str, skill_name: str) -> SkillDetailResponse:
    try:
        path = agent_dir(agent_type)
        if not path.is_dir():
            raise AgentConfigError(f"Agent 不存在: {agent_type}")
        sm = skills_manager_for_agent(agent_type)
        key = SkillsManager.validate_skill_name(skill_name)
        found = sm.find_skill(key)
        if not found:
            raise AgentConfigError(f"Skill 不存在: {key}")
        entry, source = found
        content = sm.load_skill(key, entry=entry)
        if content is None:
            raise AgentConfigError(f"Skill 不存在: {key}")
        in_builtin = source == SKILL_SOURCE_BUILTIN
        remark_entry = get_skill_remark_entry(key) if source == SKILL_SOURCE_BUILTIN else None
        return SkillDetailResponse(
            name=key,
            source=source,
            editable=in_builtin or source == SKILL_SOURCE_EXTERNAL,
            deletable=in_builtin and sm.is_skill_deletable(key),
            content=content,
            description=entry.description or "",
            category=entry.category or "general",
            remark=remark_entry["remark"] if remark_entry else "",
            remark_editable=source == SKILL_SOURCE_BUILTIN,
            remark_updated_at=remark_entry.get("updated_at") if remark_entry else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.post(
    "/config/{agent_type}/skills",
    summary="新建 Skill（写入 data/skills）",
    status_code=201,
)
async def create_agent_skill_api(agent_type: str, body: SkillCreateRequest) -> Dict[str, Any]:
    try:
        path = agent_dir(agent_type)
        if not path.is_dir():
            raise AgentConfigError(f"Agent 不存在: {agent_type}")
        sm = skills_manager_for_agent(agent_type)
        result = sm.create_skill(
            body.name,
            description=body.description,
            category=body.category,
            content=body.content,
        )
        return {"skill": result, "catalog": build_catalog(path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.put(
    "/config/{agent_type}/skills/{skill_name}/remark",
    summary="更新 Skill 用户备注（data/skills/.remarks.json）",
)
async def update_agent_skill_remark_api(
    agent_type: str,
    skill_name: str,
    body: SkillRemarkUpdateRequest,
) -> Dict[str, Any]:
    try:
        path = agent_dir(agent_type)
        if not path.is_dir():
            raise AgentConfigError(f"Agent 不存在: {agent_type}")
        sm = skills_manager_for_agent(agent_type)
        key = SkillsManager.validate_skill_name(skill_name)
        found = sm.find_skill(key)
        if not found:
            raise AgentConfigError(f"Skill 不存在: {key}")
        _entry, source = found
        if source != SKILL_SOURCE_BUILTIN:
            raise AgentConfigError("仅 data/skills 内 Skill 可添加备注，外部 Skill 不支持")
        result = set_skill_remark(key, body.remark)
        return {"skill": result, "catalog": build_catalog(path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.put(
    "/config/{agent_type}/skills/{skill_name}/content",
    summary="写入 Skill 文件（builtin；external 会先 fork 到 builtin）",
)
async def update_agent_skill_content_api(
    agent_type: str,
    skill_name: str,
    body: SkillFileUpdateRequest,
) -> Dict[str, Any]:
    try:
        path = agent_dir(agent_type)
        if not path.is_dir():
            raise AgentConfigError(f"Agent 不存在: {agent_type}")
        sm = skills_manager_for_agent(agent_type)
        key = SkillsManager.validate_skill_name(skill_name)
        found = sm.find_skill(key)
        if not found:
            raise AgentConfigError(f"Skill 不存在: {key}")
        _entry, source = found
        if source not in (SKILL_SOURCE_BUILTIN, SKILL_SOURCE_EXTERNAL):
            raise AgentConfigError(f"Skill 不可编辑: {key}")
        result = sm.write_skill_file(key, body.file_path, body.content)
        return {"skill": result, "catalog": build_catalog(path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.delete(
    "/config/{agent_type}/skills/{skill_name}",
    summary="删除 Skill（仅 data/skills 内）",
    status_code=200,
)
async def delete_agent_skill_api(agent_type: str, skill_name: str) -> Dict[str, Any]:
    try:
        path = agent_dir(agent_type)
        if not path.is_dir():
            raise AgentConfigError(f"Agent 不存在: {agent_type}")
        sm = skills_manager_for_agent(agent_type)
        key = SkillsManager.validate_skill_name(skill_name)
        result = sm.delete_skill(key)
        remove_skill_remark(key)
        if get_lock_entry(key):
            remove_lock_entry(key)
            invalidate_preinstalled_cache()
        return {"skill": result, "catalog": build_catalog(path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AgentConfigError as e:
        raise config_error_to_http(e) from e
