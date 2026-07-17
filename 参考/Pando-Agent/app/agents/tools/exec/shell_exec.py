import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ...schemes import AgentContext, RuntimeContext
from .process_manager import PROCESS_MANAGER
from .shell_common import (
    create_command_process,
    default_deny_patterns,
    guard_command,
    resolve_working_dir,
    truncate_output,
)


@register_tool(name="shell_exec", toolset="exec")
class ExecTool(BaseTool):
    """Tool to execute shell commands."""

    def __init__(
        self,
        timeout: int = 120,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
    ):
        self.timeout = timeout
        self.deny_patterns = deny_patterns or default_deny_patterns()
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallel(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        base = """Execute a shell command and return its output.

Usage:
- Use this tool for terminal operations.
- Do not use this tool for file read/write/search/edit when dedicated tools are available.
- Default working directory is the agent workspace when `working_dir` is omitted.
- Use `working_dir` only when you need a subdirectory. Avoid `cd <dir> && <command>` patterns.
- Always quote paths that contain spaces with double quotes.
- `timeout` is in milliseconds. If omitted, the default timeout is 120000ms.
- For long-running commands (servers, test suites, builds), use `background=true`, then use `shell_process`.
- After background start: use `shell_process(wait)` if you need the final result before continuing; use `poll` only for progress checks while doing other work (do not poll in a tight loop).
- Do not use shell-level `&`, `nohup`, `disown`, or `start /b`; use `background=true` instead.
- If running multiple shell commands in one turn, combine with `&&` when order matters, or `;` when later commands should run even if earlier ones fail. Shell commands do not run in parallel with each other.
"""
        if sys.platform == "win32":
            base += " On Windows, commands run in PowerShell."
        return base

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory; defaults to the agent workspace",
                },
                "timeout": {
                    "type": "number",
                    "description": "Optional timeout in milliseconds (foreground only).",
                },
                "background": {
                    "type": "boolean",
                    "default": False,
                    "description": "Run in background and return a session_id for shell_process",
                },
                "description": {
                    "type": "string",
                    "description": "Optional short description of what this command does.",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        command: str,
        working_dir: str | None = None,
        timeout: float | None = None,
        background: bool = False,
        description: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        _ = description
        cwd = resolve_working_dir(working_dir, agent_ctx.workspace_path)

        try:
            cwd_path = Path(cwd).expanduser().resolve()
        except Exception:
            return ToolErrorResult(f"Invalid working_dir: {cwd!r}")

        workspace_root = (agent_ctx.workspace_path or "").strip() or None
        restrict_enabled = self.restrict_to_workspace or bool(workspace_root)

        guard_error = guard_command(
            command,
            str(cwd_path),
            deny_patterns=self.deny_patterns,
            allow_patterns=self.allow_patterns,
            restrict_to_workspace=restrict_enabled,
            workspace_root=workspace_root,
            background=background,
        )
        if guard_error:
            return ToolErrorResult(guard_error)

        if background:
            try:
                session = await PROCESS_MANAGER.start(
                    command=command,
                    cwd=str(cwd_path),
                    agent_session_id=agent_ctx.session_id or "",
                )
                payload = {
                    "session_id": session.session_id,
                    "pid": session.process.pid,
                    "status": session.status,
                    "command": session.command,
                }
                return ToolSuccessResult(json.dumps(payload, ensure_ascii=False))
            except Exception as e:
                logging.exception("Failed to start background command: %s", e)
                return ToolErrorResult(f"Error starting background command: {e}")

        timeout_sec = self.timeout
        if timeout is not None:
            if timeout < 0:
                return ToolErrorResult(f"Invalid timeout value: {timeout}. Timeout must be a positive number.")
            timeout_sec = max(1, int(float(timeout) / 1000))

        try:
            process = await create_command_process(command, str(cwd_path))
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return ToolErrorResult(f"Error: Command timed out after {timeout_sec} seconds")
            except asyncio.CancelledError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                raise

            returncode = process.returncode or 0
            output_parts = []
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")
            if returncode != 0:
                output_parts.append(f"\nExit code: {returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"
            return ToolSuccessResult(truncate_output(result))

        except Exception as e:
            msg = str(e) or repr(e)
            logging.error("Error executing command: %s (type=%s)", msg, type(e).__name__)
            return ToolErrorResult(f"Error executing command: {msg}")
