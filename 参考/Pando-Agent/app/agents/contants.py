from pathlib import Path
from typing import Optional
from app.config.settings import settings


# ===============Ageng相关的配置文件===========
AGENT_CONFIG_DIR = Path(settings.runtime_data_dir) / "agents"
AGENT_CONTEXT_PATH = "prompts"
AGENT_CONTEXT_FILES = ["AGENT.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md", "RUNTIME.md"]
AGENT_CONFIG_FILE = "config.json"
AGENT_TYPE_PLANNING = "Planning"
PLANNING_PROMPT_USER = "PLANNING_USER.md"
PLANNING_PROMPT_JUDGE_USER = "JUDGE_USER.md"


def is_planning_agent_type(agent_type: str) -> bool:
    """会话 agent_type 为 Planning 时走 PlanningAgent 执行器。"""
    return (agent_type or "").strip().lower() == AGENT_TYPE_PLANNING.lower()


# ==============存放技能的目录===============
SKILLS_DIR_NAME = "skills"
MEMORY_DIR_NAME = ".memory"

BUILTIN_SKILLS_DIR = (Path(settings.runtime_data_dir) / SKILLS_DIR_NAME).resolve()

def workspace_skills_dir(workspace_path: Path | str | None) -> Path | None:
    if not workspace_path:
        return None
    candidate = Path(workspace_path).expanduser().resolve() / SKILLS_DIR_NAME
    return candidate if candidate.is_dir() else None

def resolve_workspace_path(
    user_id: str,
    agent_type: str,
    workspace_path: Optional[str] = None,
) -> Path:
    """有 workspace_path 则用用户路径，否则默认沙箱 data/.workspace/{user_id}/{agent_type}/。"""
    raw = (workspace_path or "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    path = (Path(settings.runtime_data_dir) / ".workspace" / user_id / agent_type).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
