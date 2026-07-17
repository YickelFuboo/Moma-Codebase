"""Agent 配置 CRUD API。"""
import json
import logging
import shutil
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from ..contants import AGENT_CONFIG_FILE
from .common import (
    AgentConfigError,
    DEFAULT_COPY_FROM,
    TEMPLATE_AGENT_DIRS,
    agent_dir,
    build_catalog,
    config_error_to_http,
    is_protected,
    load_config,
    load_meta,
    load_prompts,
    prompts_dir,
    resolved_agents_root,
    validate_agent_type,
)


router = APIRouter()


class AgentTypeItem(BaseModel):
    """单个 Agent 类型：类型标识、中文名称、中文描述。"""
    agent_type: str = Field(..., description="Agent 类型标识，即目录名")
    name: str = Field(..., description="Agent 中文名称")
    description: str = Field(default="", description="Agent 中文简介")
    protected: bool = Field(default=False, description="是否受保护不可删除")


class AgentTypesResponse(BaseModel):
    """支持的 Agent 类型列表（含名称与描述）。"""
    items: List[AgentTypeItem] = Field(..., description="Agent 类型列表，含名称与描述")


class AgentCreateRequest(BaseModel):
    agent_type: str = Field(..., description="新 Agent 目录名")
    name_zh: Optional[str] = Field(default=None, description="中文名称，写入 config.json")
    copy_from: str = Field(default=".example", description="复制模板的 Agent 目录名")


class AgentUpdateRequest(BaseModel):
    config: Dict[str, Any] = Field(..., description="config.json 完整内容")
    prompts: Dict[str, str] = Field(
        default_factory=dict,
        description="prompts 目录下相对路径 -> 文件内容，如 AGENT.md",
    )


class AgentDetailResponse(BaseModel):
    agent_type: str
    name: str
    description: str = ""
    protected: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)
    prompts: Dict[str, str] = Field(default_factory=dict)
    catalog: Dict[str, Any] = Field(
        default_factory=dict,
        description="系统工具集/工具与可用 Skill 目录，供前端结构化编辑",
    )


def _list_agents(*, include_internal: bool = False) -> List[Dict[str, Any]]:
    root = resolved_agents_root()
    items: List[Dict[str, Any]] = []
    if not root.is_dir():
        return items
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        name, description, internal = load_meta(p)
        if internal and not include_internal:
            continue
        items.append(
            {
                "agent_type": p.name,
                "name": name,
                "description": description,
                "protected": is_protected(p.name),
                "internal": internal,
            }
        )
    return items


def _get_agent_detail(agent_type: str) -> Dict[str, Any]:
    path = agent_dir(agent_type)
    if not path.is_dir():
        raise AgentConfigError(f"Agent 不存在: {agent_type}")
    config = load_config(path)
    name, description, _internal = load_meta(path)
    return {
        "agent_type": agent_type,
        "name": name,
        "description": description,
        "protected": is_protected(agent_type),
        "config": config,
        "prompts": load_prompts(path),
        "catalog": build_catalog(path),
    }


def _create_agent(
    agent_type: str,
    name_zh: Optional[str] = None,
    copy_from: str = DEFAULT_COPY_FROM,
) -> Dict[str, Any]:
    key = validate_agent_type(agent_type)
    dest = agent_dir(key)
    if dest.exists():
        raise AgentConfigError(f"Agent 已存在: {key}")
    source_name = (copy_from or DEFAULT_COPY_FROM).strip()
    root = resolved_agents_root()
    if source_name in TEMPLATE_AGENT_DIRS:
        source = (root / source_name).resolve()
        if source.parent != root:
            raise AgentConfigError("非法模板路径")
    else:
        if source_name.startswith("."):
            raise AgentConfigError("不能从隐藏目录复制")
        source = agent_dir(source_name)
    if not source.is_dir():
        raise AgentConfigError(f"模板 Agent 不存在: {source_name}")
    shutil.copytree(source, dest)
    if name_zh:
        cfg_path = dest / AGENT_CONFIG_FILE
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["name_zh"] = name_zh.strip()
                cfg_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except Exception as e:
            logging.warning("Failed to set name_zh for new agent %s: %s", key, e)
    return _get_agent_detail(key)


def _update_agent(
    agent_type: str,
    config: Dict[str, Any],
    prompts: Dict[str, str],
) -> Dict[str, Any]:
    path = agent_dir(agent_type)
    if not path.is_dir():
        raise AgentConfigError(f"Agent 不存在: {agent_type}")
    if not isinstance(config, dict):
        raise AgentConfigError("config 须为 JSON 对象")
    cfg_path = path / AGENT_CONFIG_FILE
    cfg_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    prompts_root = prompts_dir(path)
    prompts_root.mkdir(parents=True, exist_ok=True)
    for rel, content in (prompts or {}).items():
        rel_key = (rel or "").strip().replace("\\", "/")
        if not rel_key or ".." in rel_key.split("/"):
            raise AgentConfigError(f"非法 Prompt 路径: {rel}")
        if not rel_key.endswith(".md"):
            raise AgentConfigError(f"Prompt 须为 .md 文件: {rel_key}")
        target = (prompts_root / rel_key).resolve()
        try:
            target.relative_to(prompts_root.resolve())
        except ValueError as e:
            raise AgentConfigError(f"非法 Prompt 路径: {rel_key}") from e
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if content is not None else "", encoding="utf-8")
    return _get_agent_detail(agent_type)


def _delete_agent(agent_type: str) -> None:
    if is_protected(agent_type):
        raise AgentConfigError(f"内置 Agent「{agent_type}」不可删除")
    path = agent_dir(agent_type)
    if not path.is_dir():
        raise AgentConfigError(f"Agent 不存在: {agent_type}")
    shutil.rmtree(path)


@router.get(
    "/types",
    summary="查询支持的 Agent 类型",
    description="返回当前支持的 Agent 类型列表，含中文名称与描述（来源于各 Agent 目录下的 config.json）",
    response_model=AgentTypesResponse,
)
async def list_agent_types(
    include_internal: bool = Query(False, description="是否包含 internal Agent（如 SubAgent，仅配置管理用）"),
) -> AgentTypesResponse:
    """查询支持的 Agent 类型列表（含名称、描述）。"""
    items = [
        AgentTypeItem(
            agent_type=x["agent_type"],
            name=x["name"],
            description=x["description"],
            protected=x.get("protected", False),
        )
        for x in _list_agents(include_internal=include_internal)
    ]
    return AgentTypesResponse(items=items)


@router.get(
    "/meta/catalog/{agent_type}",
    summary="获取 Agent 工具与 Skill 目录",
)
async def get_agent_catalog(agent_type: str) -> Dict[str, Any]:
    try:
        path = agent_dir(agent_type)
        if not path.is_dir():
            raise AgentConfigError(f"Agent 不存在: {agent_type}")
        return build_catalog(path)
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.get(
    "/config/{agent_type}",
    summary="获取 Agent 配置详情",
    response_model=AgentDetailResponse,
)
async def get_agent(agent_type: str) -> AgentDetailResponse:
    try:
        data = _get_agent_detail(agent_type)
        return AgentDetailResponse(**data)
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.post(
    "/create",
    summary="新增 Agent",
    response_model=AgentDetailResponse,
    status_code=201,
)
async def create_agent_api(body: AgentCreateRequest) -> AgentDetailResponse:
    try:
        data = _create_agent(
            body.agent_type,
            name_zh=body.name_zh,
            copy_from=body.copy_from,
        )
        return AgentDetailResponse(**data)
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.put(
    "/config/{agent_type}",
    summary="更新 Agent 配置与 Prompt",
    response_model=AgentDetailResponse,
)
async def update_agent_api(agent_type: str, body: AgentUpdateRequest) -> AgentDetailResponse:
    try:
        data = _update_agent(agent_type, body.config, body.prompts)
        return AgentDetailResponse(**data)
    except AgentConfigError as e:
        raise config_error_to_http(e) from e


@router.delete(
    "/config/{agent_type}",
    summary="删除 Agent",
    status_code=204,
)
async def delete_agent_api(agent_type: str) -> None:
    try:
        _delete_agent(agent_type)
    except AgentConfigError as e:
        raise config_error_to_http(e) from e
