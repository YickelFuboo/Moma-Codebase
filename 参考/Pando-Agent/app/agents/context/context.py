import base64
import logging
import mimetypes
import os
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from app.infrastructure.llms.prompts.prompt_template_load import get_prompt_template
from ..contants import AGENT_CONTEXT_PATH, AGENT_CONTEXT_FILES, BUILTIN_SKILLS_DIR
from ..memorys.base import BaseMemoryManager
from ..schemes import AgentContext
from ..skills.manager import SkillsManager


class ContextBuilder:

    def __init__(
        self,
        ctx: AgentContext,
        skills_manager: SkillsManager | None = None,
        memory_manager: BaseMemoryManager | None = None,
    ):
        self.ctx = ctx
        self.skills_manager = skills_manager
        self.memory_manager = memory_manager

    @staticmethod
    def _detect_shell_name() -> str:
        shell_path = os.environ.get("SHELL") or os.environ.get("ComSpec") or ""
        shell_name = Path(shell_path).name.strip().lower()
        if "powershell" in shell_name or "pwsh" in shell_name:
            return "powershell"
        if "cmd.exe" in shell_name or shell_name == "cmd":
            return "cmd"
        if "bash" in shell_name:
            return "bash"
        if "zsh" in shell_name:
            return "zsh"
        return shell_name or "unknown"

    @staticmethod
    def _load_workspace_project_rules(workspace_path: str) -> str | None:
        """加载工作区项目约定（对标 Claude Code CLAUDE.md）：.agent/rules.md，其次 AGENTS.md。"""
        root = Path(workspace_path).expanduser().resolve()
        candidates = [
            root / ".agent" / "rules.md",
            root / "AGENTS.md",
        ]
        chunks: list[str] = []
        for path in candidates:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                logging.warning("Failed to read project rules %s: %s", path, exc)
                continue
            if not text:
                continue
            rel = path.relative_to(root).as_posix()
            chunks.append(f"## {rel}\n\n{text}")
            if path.name == "rules.md":
                break
        if not chunks:
            return None
        return "# Project Rules\n\n" + "\n\n".join(chunks)

    async def build_system_prompt(self) -> str:
        """
        拼出完整的 system prompt 字符串。
        顺序：身份与约定 → 引导文件 → 记忆 → 常驻技能全文 → 技能摘要（按需 skill_view）。
        filter_skills 由 Agent.skills_manager 根据 config 注入。
        """
        parts = []

        # 获取模板参数
        system = platform.system()
        shell_name = self._detect_shell_name()
        runtime = (
            f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, "
            f"Python {platform.python_version()}, Shell {shell_name}"
        )

        params = self.ctx.params_dict()
        params.update({
            "runtime": runtime,
            "workspace_path": str(Path(self.ctx.workspace_path).expanduser().resolve()),
            "agent_type": self.ctx.agent_type or "",
            "skills_dir": str(BUILTIN_SKILLS_DIR),
        })

        # 1. 构造Agent类型对应的引导文件（从 .agent/agent_type/prompt 目录读）
        agent_prompt_dir = Path(self.ctx.agent_path) / AGENT_CONTEXT_PATH
        for filename in AGENT_CONTEXT_FILES:
            file = agent_prompt_dir / filename
            if file.exists():
                content = get_prompt_template(str(agent_prompt_dir), filename, params)
                if content:
                    parts.append(f"{content}")

        project_rules = self._load_workspace_project_rules(params["workspace_path"])
        if project_rules:
            parts.append(project_rules)

        # 2. 长期记忆：组合三层记忆（会话/工作空间/Agent 类型）
        if self.memory_manager is not None:
            memory = await self.memory_manager.get_memory_context()
            if memory:
                parts.append(f"# Memory\n\n{memory}")

        # 3. 技能分两种：常驻技能直接全文放入；其余只给摘要，让 Agent 用 skill_view 按需加载
        if self.skills_manager:
            always_content = self.skills_manager.get_always_skills_content_for_context()
            has_always_skills = bool(always_content)
            if has_always_skills:
                parts.append(
                    "# Always Skills\n\n"
                    "The skills below (always=true) are fully loaded in this prompt. Follow their instructions directly; "
                    "do not call skill_view again for the same names unless you need linked_files.\n\n"
                    f"{always_content}"
                )

            skills_summary = self.skills_manager.build_skills_summary()
            if skills_summary:
                parts.append(
                    self._build_skills_section(
                        skills_summary,
                        has_always_skills=has_always_skills,
                        skill_manage_enabled=self.skills_manager.allow_manage,
                    )
                )

        # 用分隔符连接各段，避免挤在一起
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _build_skills_section(
        skills_summary: str,
        *,
        has_always_skills: bool,
        skill_manage_enabled: bool = False,
    ) -> str:
        always_note = (
            "- **# Always Skills** (above) are already fully loaded — follow them; skip skill_view for those names unless you need linked_files.\n"
            if has_always_skills
            else ""
        )
        manage_note = (
            "7. **Maintenance**: use `skill_manage(action=\"create\"|\"delete\"|\"replace\"|\"write_file\", ...)` "
            "to create/delete skills or edit files under data/skills. "
            "Project workspace skills (`source=workspace`) are read-only. "
            "Do not use filesystem tools on skill paths.\n"
            if skill_manage_enabled
            else ""
        )
        return f"""# Skills (mandatory)

Skills provide specialized workflows. The index below lists **name + description only** — insufficient to execute.

## Before you reply

1. **Scan** the index (grouped by `<category>`). If any `<description>` matches the user's task, you **MUST** call `skill_view(name="...")` with the exact `<name>` **before** substantive answers or actions covered by that skill.
2. **Never** load skills via `read_file` or filesystem paths. Use `skill_view(name)` only — do not guess skill content from summaries.
3. If `skill_view` returns `linked_files`, load attachments with `skill_view(name, file_path="references/...")` (or templates/scripts/assets paths listed).
4. Refresh or filter: `skills_list()` or `skills_list(category="etf")` (matches directory layout `skills/<category>/<name>/`).
5. **Project skills**: `<workspace>/skills/` under the current working directory are loaded automatically (`source=workspace`, read-only). Use `skill_view` only — do not edit or install them via `skill_manage` / `skill_hub`.
6. **Hub**: use `skill_hub` to discover/install skills into the global `data/skills` catalog (not workspace):
   - `search` with `source`: `all|builtin|github|clawhub|skills-sh|well-known|lobehub` — ClawHub/A-share use `source=clawhub`; well-known use `source=well-known` with host like `developers.cloudflare.com`; LobeHub use `source=lobehub`
   - `inspect` / `install` identifiers: `builtin:cron`, `github:openai/skills/pdf`, `clawhub:<slug>`, `skills-sh:owner/repo/skill`, `well-known:host/skill`, `lobehub:<identifier>` (common URLs also accepted)
   - `list_installed`, `uninstall`, `check`, `update`, `audit` for hub-managed skills; `list_taps` / `add_tap` / `remove_tap` for custom GitHub repos
{always_note}{manage_note}
## Unavailable skills

If `<skill available="false">`, read `<requires>` / `setup_needed` from `skill_view`, install missing CLI tools (apt/brew/pip) or set required environment variables, then retry `skill_view`.

## Index

{skills_summary}"""
    
    async def build_user_content(
        self,
        content: str,
        media: list[str] | None = None
    ) -> str | list[dict[str, Any]]:

        # 最后一条：当前用户输入（支持多模态图片）+ 末尾注入时间、channel、chat_id
        user_content = self._process_media_content(content, media)
        user_content = self._inject_runtime_context(user_content)

        return user_content

    def _process_media_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """
        把当前用户消息做成 LLM 可用的 content：无媒体则返回纯文本；
        有媒体则只处理图片，转成 base64 data URL，与文本组成多模态列表（先图后文）。
        """
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if not images:
            return text
        return images + [{"type": "text", "text": text}]

        
    @staticmethod
    def _inject_runtime_context(
        content: str | list[dict[str, Any]],
    ) -> str | list[dict[str, Any]]:
        """
        在当前用户消息末尾追加「运行时上下文」：当前时间、时区。
        - 若 user_content 是字符串：直接拼在后面。
        - 若是多模态列表（如图+文）：追加一个 text 块，保证 LLM 能看到时间与来源。
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        block = "[Runtime Context]\n" + "\n".join(lines)
        if isinstance(content, str):
            return f"{content}\n\n{block}"
        return [*content, {"type": "text", "text": block}]