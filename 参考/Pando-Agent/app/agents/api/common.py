"""Agent / Skill API 共享工具与 catalog 构建。"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from fastapi import HTTPException
from ..contants import AGENT_CONFIG_DIR, AGENT_CONFIG_FILE, AGENT_CONTEXT_PATH

AGENT_TYPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
PROTECTED_AGENT_DIRS = frozenset({".example", "SubAgent"})
DEFAULT_COPY_FROM = ".example"
TEMPLATE_AGENT_DIRS = frozenset({".example"})


class AgentConfigError(ValueError):
    """Agent 配置业务错误。"""


def config_error_to_http(exc: AgentConfigError) -> HTTPException:
    msg = str(exc)
    status = 404 if "不存在" in msg else 409 if "已存在" in msg else 400
    return HTTPException(status_code=status, detail=msg)


def resolved_agents_root() -> Path:
    root = AGENT_CONFIG_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_agent_type(agent_type: str) -> str:
    key = (agent_type or "").strip()
    if not key or not AGENT_TYPE_PATTERN.match(key):
        raise AgentConfigError(
            "agent_type 须以字母开头，仅含字母、数字、下划线与连字符"
        )
    if key.startswith("."):
        raise AgentConfigError("agent_type 不能以 . 开头")
    return key


def agent_dir(agent_type: str) -> Path:
    key = validate_agent_type(agent_type)
    root = resolved_agents_root()
    path = (root / key).resolve()
    if path.parent != root:
        raise AgentConfigError("非法 agent_type")
    return path


def is_protected(agent_type: str) -> bool:
    return agent_type in PROTECTED_AGENT_DIRS


def load_meta(agent_dir_path: Path) -> Tuple[str, str, bool]:
    path = agent_dir_path / AGENT_CONFIG_FILE
    if not path.is_file():
        return agent_dir_path.name, "", False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return agent_dir_path.name, "", False
        name = data.get("name_zh") or agent_dir_path.name
        desc = data.get("description_zh") or ""
        internal = bool(data.get("internal"))
        return str(name), str(desc), internal
    except Exception as e:
        logging.warning("Failed to load agent meta for %s: %s", agent_dir_path.name, e)
        return agent_dir_path.name, "", False


def prompts_dir(agent_dir_path: Path) -> Path:
    return agent_dir_path / AGENT_CONTEXT_PATH


def load_prompts(agent_dir_path: Path) -> Dict[str, str]:
    prompts: Dict[str, str] = {}
    prompts_path = prompts_dir(agent_dir_path)
    if not prompts_path.is_dir():
        return prompts
    for f in sorted(prompts_path.rglob("*.md")):
        if not f.is_file():
            continue
        rel = f.relative_to(prompts_path).as_posix()
        try:
            prompts[rel] = f.read_text(encoding="utf-8")
        except Exception as e:
            logging.warning("Failed to read prompt %s: %s", f, e)
            prompts[rel] = ""
    return prompts


def load_config(agent_dir_path: Path) -> Dict[str, Any]:
    path = agent_dir_path / AGENT_CONFIG_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as e:
        raise AgentConfigError(f"config.json 不是合法 JSON: {e}") from e


def parse_external_dirs(config: Dict[str, Any]) -> List[str]:
    skills = config.get("skills") if isinstance(config, dict) else None
    if not isinstance(skills, dict):
        return []
    raw = skills.get("external_dirs")
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def skills_manager_for_agent(agent_type: str, config: Dict[str, Any] | None = None):
    from ..skills.manager import SkillsManager

    key = validate_agent_type(agent_type)
    path = agent_dir(key)
    if config is None:
        config = load_config(path)
    external = parse_external_dirs(config)
    return SkillsManager(key, external_dirs=external or None)


def build_catalog(agent_dir_path: Path) -> Dict[str, Any]:
    from ..tools.catalog import catalog_toolsets, ensure_tools_catalog_loaded, tool_names_for_toolset
    from ..skills.hub import HUB_SERVICE
    from ..skills.manager import SKILL_SOURCE_BUILTIN
    from ..skills.paths import DEFAULT_SKILL_CATEGORY
    from ..skills.remarks import get_skill_remark_entry

    ensure_tools_catalog_loaded()
    toolsets = [
        {"name": ts, "tools": tool_names_for_toolset(ts)}
        for ts in catalog_toolsets()
    ]
    config = load_config(agent_dir_path)
    sm = skills_manager_for_agent(agent_dir_path.name, config)
    skills: List[Dict[str, str]] = []
    for item in sm.list_skills(filter_unavailable=False):
        name = item["name"]
        desc = item.get("description") or ""
        source = item.get("source") or SKILL_SOURCE_BUILTIN
        row: Dict[str, Any] = {
            "name": name,
            "description": desc,
            "category": item.get("category") or DEFAULT_SKILL_CATEGORY,
            "source": source,
        }
        if source == SKILL_SOURCE_BUILTIN:
            remark_entry = get_skill_remark_entry(name)
            row["remark"] = remark_entry["remark"] if remark_entry else ""
            if remark_entry and remark_entry.get("updated_at"):
                row["remark_updated_at"] = remark_entry["updated_at"]
        hub_meta = HUB_SERVICE.hub_metadata_for_skill(name)
        if hub_meta:
            row["source"] = "hub"
            row.update(hub_meta)
        skills.append(row)
    return {"toolsets": toolsets, "skills": skills, "hub_installed": HUB_SERVICE.list_installed()}
