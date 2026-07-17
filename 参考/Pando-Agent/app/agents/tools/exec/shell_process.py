import json
from typing import Any
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ...schemes import AgentContext, RuntimeContext
from .process_manager import PROCESS_MANAGER
from .shell_common import truncate_output


@register_tool(name="shell_process", toolset="exec")
class ShellProcessTool(BaseTool):
    """管理 shell_exec(background=true) 启动的后台进程。"""

    @property
    def name(self) -> str:
        return "shell_process"

    @property
    def description(self) -> str:
        return """Manage background processes started with shell_exec(background=true).

Actions:
- list: show background processes for the current agent session
- wait: block until the process exits (optional timeout in milliseconds). Prefer this when you need the final result before continuing.
- poll: fetch new stdout/stderr since the last poll. Use for occasional progress checks while doing other work; do not poll in a tight loop.
- log: return full accumulated output so far
- kill: terminate the process

While status is running, poll/log return partial output. wait returns the full result when the process finishes.
"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "poll", "log", "wait", "kill"],
                    "description": "Process management action",
                },
                "session_id": {
                    "type": "string",
                    "description": "Background session id returned by shell_exec",
                },
                "timeout": {
                    "type": "number",
                    "description": "For wait: timeout in milliseconds",
                },
            },
            "required": ["action"],
        }

    @property
    def is_readonly(self) -> bool:
        return False

    @property
    def is_parallel(self) -> bool:
        return False

    async def execute(
        self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
        action: str,
        session_id: str | None = None,
        timeout: float | None = None,
    ) -> ToolResult:
        action_name = (action or "").strip().lower()
        agent_session_id = agent_ctx.session_id or ""

        if action_name == "list":
            sessions = await PROCESS_MANAGER.list_sessions(agent_session_id)
            items = [
                {
                    "session_id": s.session_id,
                    "pid": s.process.pid,
                    "status": s.status,
                    "command": s.command,
                    "returncode": s.returncode,
                }
                for s in sessions
            ]
            return ToolSuccessResult(json.dumps({"processes": items}, ensure_ascii=False))

        if not session_id:
            return ToolErrorResult("session_id is required for this action")

        owned = await PROCESS_MANAGER.get(session_id)
        if owned is None:
            return ToolErrorResult(json.dumps({"error": f"Unknown session_id: {session_id}"}, ensure_ascii=False))
        if owned.agent_session_id:
            if not agent_session_id or owned.agent_session_id != agent_session_id:
                return ToolErrorResult(json.dumps({"error": "session_id not found in this agent session"}, ensure_ascii=False))

        timeout_sec = None
        if timeout is not None:
            if timeout < 0:
                return ToolErrorResult(f"Invalid timeout value: {timeout}")
            timeout_sec = max(1, int(float(timeout) / 1000))

        if action_name == "poll":
            result = await PROCESS_MANAGER.poll(session_id)
        elif action_name == "log":
            result = await PROCESS_MANAGER.log(session_id)
        elif action_name == "wait":
            result = await PROCESS_MANAGER.wait(session_id, timeout_sec, run_ctx=run_ctx)
            if result.get("aborted"):
                if run_ctx.is_aborted():
                    return run_ctx.aborted_tool_result(self.name)
                return ToolErrorResult("shell_process wait failed: no result")
        elif action_name == "kill":
            result = await PROCESS_MANAGER.kill(session_id)
        else:
            return ToolErrorResult(f"Unknown action: {action}")

        if result.get("error"):
            return ToolErrorResult(json.dumps(result, ensure_ascii=False))

        for key in ("stdout", "stderr"):
            if key in result and isinstance(result[key], str):
                result[key] = truncate_output(result[key])

        return ToolSuccessResult(json.dumps(result, ensure_ascii=False))
