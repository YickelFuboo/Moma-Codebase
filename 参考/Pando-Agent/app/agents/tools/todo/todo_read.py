import json
from pathlib import Path
from typing import Any,Dict,List,Optional
from ..catalog import register_tool
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult
from ...schemes import AgentContext, RuntimeContext
from .utils import todo_file


def _load(path : Path)->List[Dict[str,Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []


@register_tool(name="todo_read", toolset="todo")
class TodoReadTool(BaseTool):

    @property
    def name(self)->str:
        return "todo_read"

    @property
    def description(self)->str:
        return """Use this tool to read the current to-do list for the session. This tool should be used proactively and frequently to ensure that you are aware of
the status of the current task list. You should make use of this tool as often as possible, especially in the following situations:
- At the beginning of conversations to see what's pending
- Before starting new tasks to prioritize work
- When the user asks about previous tasks or plans
- Whenever you're uncertain about what to do next
- After completing tasks to update your understanding of remaining work
- After every few messages to ensure you're on track

Usage:
- This tool takes in no parameters. So leave the input blank or empty. DO NOT include a dummy object, placeholder string or a key like "input" or "empty". LEAVE IT BLANK.
- Returns a list of todo items with their status, priority, and content
- Use this information to track progress and plan next steps
- If no todos exist yet, an empty list will be returned"""

    @property
    def parameters(self)->Dict[str,Any]:
        return {"type":"object","properties":{}}

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_parallel(self) -> bool:
        return True

    async def execute(self,
        agent_ctx: AgentContext,
        run_ctx: RuntimeContext,
    ) -> ToolResult:
        session_id = agent_ctx.session_id or ""
        if not session_id:
            return ToolErrorResult("todo_read: session_id is required")

        p = todo_file(session_id)
        todos = _load(p)
        remaining = len([t for t in todos if t.get("status")!="completed"])
        output="\n".join([
            f"<path>{p.resolve()}</path>",
            f"<remaining>{remaining}</remaining>",
            "<todos>",
            json.dumps(todos,ensure_ascii=False,indent=2),
            "</todos>",
        ])
        return ToolSuccessResult(output)

